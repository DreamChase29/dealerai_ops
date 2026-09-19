"""Executable Agent Evaluation Laboratory runner."""

import argparse
import csv
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dealerai_ops.agents.orchestrator import AgentOrchestrator
from dealerai_ops.agents.providers import ScriptedLLMProvider
from dealerai_ops.agents.schemas import (
    AgentRunRequest,
    AgentRunResult,
    ConversationState,
    ToolRequest,
)
from dealerai_ops.db.base import Base
from dealerai_ops.db.models import Conversation
from dealerai_ops.db.session import create_db_engine, create_session_factory
from dealerai_ops.domain.synthetic import (
    DEFAULT_SYNTHETIC_SEED,
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    seed_session,
)
from dealerai_ops.evals.scenarios import ScenarioContext, build_evaluation_scenarios
from dealerai_ops.evals.schemas import (
    AggregateMetrics,
    EvaluationResult,
    EvaluationRunReport,
    EvaluationScenario,
    ExecutionMetadata,
    ScoreResult,
)
from dealerai_ops.evals.scorers import ScoringContext, score_scenario
from dealerai_ops.ml.schemas import NoShowPredictionRequest, NoShowPredictionResponse, RiskTier
from dealerai_ops.rag.retriever import KnowledgeRetriever, build_local_retriever
from dealerai_ops.tools.executor import ToolExecutor

DEFAULT_OUTPUT_DIR = Path("evaluation/results")
DEFAULT_KNOWLEDGE_DIR = Path("knowledge")
EVAL_AS_OF = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
EVAL_COUNTS = SyntheticDatasetCounts(
    customers=80,
    owned_vehicles=100,
    inventory_vehicles=40,
    historical_appointments=180,
    future_service_days=15,
    sales_leads=40,
    conversations=30,
    tool_executions=0,
    escalations=0,
)


class StaticNoShowPredictionService:
    """Deterministic no-show predictor used by evaluation runs."""

    def predict(self, request: NoShowPredictionRequest) -> NoShowPredictionResponse:
        """Return a stable operational risk response."""
        del request
        return NoShowPredictionResponse(
            probability=0.42,
            risk_tier=RiskTier.HIGH,
            model_version="eval-static-no-show-v1",
        )


def run_evaluation(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR,
    limit: int | None = None,
    input_price_per_1k: float | None = None,
    output_price_per_1k: float | None = None,
) -> EvaluationRunReport:
    """Run deterministic scenarios and write JSON, CSV, and Markdown reports."""
    scenarios = _scenarios(limit)
    retriever = build_local_retriever(knowledge_dir)
    results = [
        _run_one_scenario(
            scenario=scenario,
            retriever=retriever,
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
        )
        for scenario in scenarios
    ]
    report = EvaluationRunReport(
        generated_at=datetime.now(UTC).isoformat(),
        aggregate_metrics=_aggregate(results),
        results=results,
    )
    _write_reports(report, output_dir)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for ``python -m evaluation.run``."""
    parser = argparse.ArgumentParser(description="Run DealerAI Ops agent evaluations.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--input-price-per-1k", type=float, default=None)
    parser.add_argument("--output-price-per-1k", type=float, default=None)
    args = parser.parse_args(argv)

    report = run_evaluation(
        output_dir=args.output_dir,
        knowledge_dir=args.knowledge_dir,
        limit=args.limit,
        input_price_per_1k=args.input_price_per_1k,
        output_price_per_1k=args.output_price_per_1k,
    )
    metrics = report.aggregate_metrics
    print(
        "Agent evaluation complete: "
        f"{metrics.passed_scenarios}/{metrics.total_scenarios} passed "
        f"({metrics.pass_rate:.1%}). Reports written to {args.output_dir}."
    )
    return 0


def _scenarios(limit: int | None = None) -> list[EvaluationScenario]:
    dataset = generate_synthetic_dataset(
        EVAL_COUNTS,
        seed=DEFAULT_SYNTHETIC_SEED,
        as_of=EVAL_AS_OF,
    )
    vehicle = dataset.vehicles[0]
    appointment = dataset.service_appointments[0]
    slot = next(slot for slot in dataset.service_slots if slot.booked_count < slot.capacity)
    other_slot = next(
        candidate
        for candidate in dataset.service_slots
        if candidate.id != slot.id and candidate.booked_count < candidate.capacity
    )
    inventory = dataset.inventory_vehicles[0]
    scenarios = build_evaluation_scenarios(
        ScenarioContext(
            customer_id=vehicle.customer_id,
            vehicle_id=vehicle.id,
            slot_id=slot.id,
            other_slot_id=other_slot.id,
            appointment_id=appointment.id,
            inventory_make=inventory.make,
            inventory_model=inventory.model,
        )
    )
    return scenarios[:limit] if limit is not None else scenarios


def _run_one_scenario(
    scenario: EvaluationScenario,
    retriever: KnowledgeRetriever,
    input_price_per_1k: float | None,
    output_price_per_1k: float | None,
) -> EvaluationResult:
    session_factory = _seeded_session_factory()
    requested_tool_arguments = _requested_tool_arguments(scenario)
    started_at = perf_counter()
    model_calls = 0

    with session_factory() as session:
        conversation_id = _conversation_id(session)
        state: ConversationState | None = None
        result: AgentRunResult | None = None
        for turn_index, turn in enumerate(scenario.turns, start=1):
            provider = ScriptedLLMProvider(turn.model_responses)
            orchestrator = AgentOrchestrator(
                provider=provider,
                tool_executor=ToolExecutor(
                    session=session,
                    no_show_service=StaticNoShowPredictionService(),
                ),
                retriever=retriever,
            )
            result = orchestrator.run(
                AgentRunRequest(
                    request_id=_request_id(scenario.id, turn_index),
                    conversation_id=conversation_id,
                    user_message=turn.user_message,
                    confirmed=turn.confirmed,
                    authenticated_customer_id=turn.authenticated_customer_id,
                    state=state,
                )
            )
            model_calls += provider.calls
            state = result.state

    if result is None:
        raise ValueError("Scenario must contain at least one turn.")

    latency_ms = (perf_counter() - started_at) * 1000
    metadata = ExecutionMetadata(
        latency_ms=latency_ms,
        model_calls=model_calls,
        tool_calls=len(result.state.tool_results),
        retrieval_count=len(result.state.retrieved_chunks),
        token_metadata={},
        estimated_cost_usd=_estimated_cost(
            token_metadata={},
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
        ),
        requested_tool_arguments=requested_tool_arguments,
    )
    scores = score_scenario(
        scenario,
        ScoringContext(
            agent_result=result,
            requested_tool_arguments=requested_tool_arguments,
        ),
    )
    return _evaluation_result(scenario, result, scores, metadata)


def _seeded_session_factory() -> sessionmaker[Session]:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        seed_session(
            session,
            generate_synthetic_dataset(
                EVAL_COUNTS,
                seed=DEFAULT_SYNTHETIC_SEED,
                as_of=EVAL_AS_OF,
            ),
        )
    return session_factory


def _conversation_id(session: Session) -> str:
    conversation_id = session.scalars(select(Conversation.id).limit(1)).one()
    return str(conversation_id)


def _request_id(scenario_id: str, turn_index: int) -> str:
    normalized = scenario_id.replace("_", "-")[:48]
    return f"eval-{normalized}-{turn_index:02d}"


def _requested_tool_arguments(scenario: EvaluationScenario) -> dict[str, list[dict[str, Any]]]:
    arguments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for turn in scenario.turns:
        for response in turn.model_responses:
            if isinstance(response, ToolRequest):
                arguments[response.tool_name].append(dict(response.arguments))
    return dict(arguments)


def _evaluation_result(
    scenario: EvaluationScenario,
    result: AgentRunResult,
    scores: list[ScoreResult],
    metadata: ExecutionMetadata,
) -> EvaluationResult:
    return EvaluationResult(
        scenario_id=scenario.id,
        category=scenario.category,
        description=scenario.description,
        passed=all(score.passed for score in scores),
        scores=scores,
        metadata=metadata,
        final_status=result.status,
        final_answer=result.final_answer,
        escalation_id=result.escalation_id,
        error_code=str(result.error.code) if result.error is not None else None,
        agent_result=result,
    )


def _aggregate(results: list[EvaluationResult]) -> AggregateMetrics:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    category_totals: dict[str, int] = defaultdict(int)
    category_passed: dict[str, int] = defaultdict(int)
    scorer_totals: dict[str, int] = defaultdict(int)
    scorer_passed: dict[str, int] = defaultdict(int)

    for result in results:
        category = result.category.value
        category_totals[category] += 1
        if result.passed:
            category_passed[category] += 1
        for score in result.scores:
            scorer_totals[score.name] += 1
            if score.passed:
                scorer_passed[score.name] += 1

    return AggregateMetrics(
        total_scenarios=total,
        passed_scenarios=passed,
        failed_scenarios=total - passed,
        pass_rate=passed / total if total else 0.0,
        category_pass_rate={
            category: category_passed[category] / count
            for category, count in sorted(category_totals.items())
        },
        scorer_pass_rate={
            scorer: scorer_passed[scorer] / count for scorer, count in sorted(scorer_totals.items())
        },
        average_latency_ms=sum(result.metadata.latency_ms for result in results) / total
        if total
        else 0.0,
        total_model_calls=sum(result.metadata.model_calls for result in results),
        total_tool_calls=sum(result.metadata.tool_calls for result in results),
        total_retrieval_count=sum(result.metadata.retrieval_count for result in results),
        estimated_cost_usd=sum(result.metadata.estimated_cost_usd for result in results),
    )


def _estimated_cost(
    token_metadata: dict[str, Any],
    input_price_per_1k: float | None,
    output_price_per_1k: float | None,
) -> float:
    if input_price_per_1k is None or output_price_per_1k is None:
        return 0.0
    input_tokens = _numeric_metadata(token_metadata.get("input_tokens"))
    output_tokens = _numeric_metadata(token_metadata.get("output_tokens"))
    return (input_tokens / 1000 * input_price_per_1k) + (output_tokens / 1000 * output_price_per_1k)


def _numeric_metadata(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _write_reports(report: EvaluationRunReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    _write_csv(report, output_dir / "latest.csv")
    (output_dir / "latest.md").write_text(_markdown_report(report), encoding="utf-8")


def _write_csv(report: EvaluationRunReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario_id",
                "category",
                "passed",
                "final_status",
                "failed_scores",
                "latency_ms",
                "model_calls",
                "tool_calls",
                "retrieval_count",
                "escalation_id",
                "error_code",
            ],
        )
        writer.writeheader()
        for result in report.results:
            writer.writerow(
                {
                    "scenario_id": result.scenario_id,
                    "category": result.category.value,
                    "passed": result.passed,
                    "final_status": result.final_status.value,
                    "failed_scores": ",".join(
                        score.name for score in result.scores if not score.passed
                    ),
                    "latency_ms": f"{result.metadata.latency_ms:.2f}",
                    "model_calls": result.metadata.model_calls,
                    "tool_calls": result.metadata.tool_calls,
                    "retrieval_count": result.metadata.retrieval_count,
                    "escalation_id": result.escalation_id or "",
                    "error_code": result.error_code or "",
                }
            )


def _markdown_report(report: EvaluationRunReport) -> str:
    metrics = report.aggregate_metrics
    lines = [
        "# DealerAI Ops Agent Evaluation Report",
        "",
        f"Generated at: `{report.generated_at}`",
        "",
        "## Aggregate Metrics",
        "",
        f"- Total scenarios: {metrics.total_scenarios}",
        f"- Passed scenarios: {metrics.passed_scenarios}",
        f"- Failed scenarios: {metrics.failed_scenarios}",
        f"- Pass rate: {metrics.pass_rate:.1%}",
        f"- Average latency: {metrics.average_latency_ms:.2f} ms",
        f"- Model calls: {metrics.total_model_calls}",
        f"- Tool calls: {metrics.total_tool_calls}",
        f"- Retrieval count: {metrics.total_retrieval_count}",
        f"- Estimated cost: ${metrics.estimated_cost_usd:.6f}",
        "",
        "## Category Pass Rates",
        "",
        "| Category | Pass Rate |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {category} | {rate:.1%} |" for category, rate in metrics.category_pass_rate.items()
    )
    lines.extend(["", "## Scorer Pass Rates", "", "| Scorer | Pass Rate |", "| --- | ---: |"])
    lines.extend(f"| {scorer} | {rate:.1%} |" for scorer, rate in metrics.scorer_pass_rate.items())
    lines.extend(["", "## Failed Cases", ""])
    failed = [result for result in report.results if not result.passed]
    if not failed:
        lines.append("No failed cases.")
    for result in failed:
        case_summary = (
            f"- `{result.scenario_id}` ({result.category.value}) "
            f"status=`{result.final_status.value}`"
        )
        lines.append(case_summary)
        for score in result.scores:
            if not score.passed:
                lines.append(f"  - `{score.name}`: `{score.details}`")
    lines.extend(
        [
            "",
            "## Individual Cases",
            "",
            "| Scenario | Category | Passed | Failed Scores |",
        ]
    )
    lines.append("| --- | --- | ---: | --- |")
    for result in report.results:
        failed_scores = ", ".join(score.name for score in result.scores if not score.passed)
        lines.append(
            f"| `{result.scenario_id}` | {result.category.value} | {result.passed} | "
            f"{failed_scores or '-'} |"
        )
    return "\n".join(lines) + "\n"
