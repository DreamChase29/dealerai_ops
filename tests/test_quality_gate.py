"""Tests for the AI regression release gate."""

from pathlib import Path

from dealerai_ops.agents.schemas import AgentRunResult, AgentStatus, ConversationState
from dealerai_ops.evals.gate import (
    QualityThresholdConfig,
    evaluate_gate,
    main,
    write_gate_report,
)
from dealerai_ops.evals.schemas import (
    AggregateMetrics,
    EvalCategory,
    EvaluationResult,
    EvaluationRunReport,
    ExecutionMetadata,
    ScoreResult,
)


def test_quality_gate_accepts_report_that_meets_thresholds() -> None:
    """A clean deterministic report should pass the default release gate shape."""
    gate = evaluate_gate(_passing_report(), _default_thresholds())

    assert gate.accepted
    assert {metric.name for metric in gate.metrics} == {
        "task_success",
        "tool_selection_accuracy",
        "transaction_consistency",
        "pii_safety_pass_rate",
        "required_escalation_recall",
        "rag_retrieval_hit_rate",
        "hallucinated_transaction_rate",
    }


def test_quality_gate_rejects_failing_metric() -> None:
    """Configured threshold failures reject the release and identify the metric."""
    report = _passing_report()
    report.results[0].scores[0] = ScoreResult(
        name="task_success",
        passed=False,
        score=0.0,
    )

    gate = evaluate_gate(report, _default_thresholds())

    assert not gate.accepted
    failing_names = {metric.name for metric in gate.metrics if not metric.passed}
    assert "task_success" in failing_names


def test_quality_gate_command_returns_nonzero_and_writes_reports(tmp_path: Path) -> None:
    """The command returns non-zero for regressions and writes artifacts."""
    results_path = tmp_path / "latest.json"
    config_path = tmp_path / "thresholds.json"
    markdown_path = tmp_path / "quality_gate.md"
    json_path = tmp_path / "quality_gate.json"
    results_path.write_text(_failing_report().model_dump_json(indent=2), encoding="utf-8")
    config_path.write_text(_default_thresholds().model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            "--results",
            str(results_path),
            "--config",
            str(config_path),
            "--markdown-output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ]
    )

    assert exit_code == 1
    assert "task_success" in markdown_path.read_text(encoding="utf-8")
    assert "accepted" in json_path.read_text(encoding="utf-8")


def test_quality_gate_report_writer_creates_human_readable_markdown(tmp_path: Path) -> None:
    """The report writer emits a Markdown artifact suitable for CI upload."""
    gate = evaluate_gate(_passing_report(), _default_thresholds())
    markdown_path = tmp_path / "quality.md"
    json_path = tmp_path / "quality.json"

    write_gate_report(gate, markdown_path=markdown_path, json_path=json_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "DealerAI Ops Quality Gate Report" in markdown
    assert "Release decision: **ACCEPTED**" in markdown
    assert json_path.exists()


def _default_thresholds() -> QualityThresholdConfig:
    return QualityThresholdConfig(
        version="unit-test",
        description="Unit test thresholds.",
        minimums={
            "task_success": 0.90,
            "tool_selection_accuracy": 0.95,
            "transaction_consistency": 1.00,
            "pii_safety_pass_rate": 1.00,
            "required_escalation_recall": 0.95,
            "rag_retrieval_hit_rate": 0.90,
        },
        maximums={"hallucinated_transaction_rate": 0.0},
    )


def _passing_report() -> EvaluationRunReport:
    results = [
        _result(EvalCategory.NORMAL_CUSTOMER, True, [_score("task_success", True)]),
        _result(
            EvalCategory.TOOL_SELECTION,
            True,
            [_score("task_success", True), _score("expected_tool_called", True)],
        ),
        _result(
            EvalCategory.TRANSACTION,
            True,
            [_score("task_success", True), _score("transaction_state_consistency", True)],
        ),
        _result(EvalCategory.PII_SAFETY, True, [_score("task_success", True)]),
        _result(
            EvalCategory.HUMAN_ESCALATION,
            True,
            [_score("task_success", True), _score("required_escalation", True)],
        ),
        _result(
            EvalCategory.RAG,
            True,
            [_score("task_success", True), _score("retrieval_hit", True)],
        ),
        _result(
            EvalCategory.HISTORICAL_REGRESSION,
            True,
            [_score("task_success", True), _score("hallucinated_transaction", True)],
        ),
    ]
    return _report(results)


def _failing_report() -> EvaluationRunReport:
    report = _passing_report()
    report.results[0].passed = False
    report.results[0].scores[0] = _score("task_success", False)
    return report


def _report(results: list[EvaluationResult]) -> EvaluationRunReport:
    return EvaluationRunReport(
        generated_at="2026-08-11T00:00:00+00:00",
        aggregate_metrics=AggregateMetrics(
            total_scenarios=len(results),
            passed_scenarios=sum(1 for result in results if result.passed),
            failed_scenarios=sum(1 for result in results if not result.passed),
            pass_rate=1.0,
            category_pass_rate={},
            scorer_pass_rate={},
            average_latency_ms=1.0,
            total_model_calls=1,
            total_tool_calls=1,
            total_retrieval_count=1,
            estimated_cost_usd=0.0,
        ),
        results=results,
    )


def _result(
    category: EvalCategory,
    passed: bool,
    scores: list[ScoreResult],
) -> EvaluationResult:
    return EvaluationResult(
        scenario_id=f"unit-{category.value}",
        category=category,
        description="Unit quality gate scenario.",
        passed=passed,
        scores=scores,
        metadata=ExecutionMetadata(
            latency_ms=1.0,
            model_calls=1,
            tool_calls=1,
            retrieval_count=1,
        ),
        final_status=AgentStatus.COMPLETED,
        agent_result=AgentRunResult(
            request_id="req_1",
            conversation_id="conv_1",
            status=AgentStatus.COMPLETED,
            state=ConversationState(conversation_id="conv_1"),
        ),
    )


def _score(name: str, passed: bool) -> ScoreResult:
    return ScoreResult(name=name, passed=passed, score=1.0 if passed else 0.0)
