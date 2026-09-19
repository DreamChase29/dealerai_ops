"""Programmatic scorers for agent evaluation results."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dealerai_ops.agents.schemas import AgentRunResult, AgentStatus
from dealerai_ops.evals.schemas import EvaluationScenario, ScoreResult
from dealerai_ops.tools.types import ToolExecutionOutcome


@dataclass(frozen=True)
class ScoringContext:
    """Runtime traces needed by scorers beyond the final agent result."""

    agent_result: AgentRunResult
    requested_tool_arguments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


Scorer = Callable[[EvaluationScenario, ScoringContext], ScoreResult]


def score_task_success(scenario: EvaluationScenario, context: ScoringContext) -> ScoreResult:
    """Score final status and expected answer substrings."""
    result = context.agent_result
    expected = scenario.expected
    status_ok = expected.expected_status is None or result.status == expected.expected_status
    answer = result.final_answer or ""
    substrings_ok = all(
        fragment.lower() in answer.lower() for fragment in expected.expected_final_contains
    )
    return _score(
        "task_success",
        status_ok and substrings_ok,
        {
            "expected_status": expected.expected_status,
            "actual_status": result.status,
            "expected_final_contains": expected.expected_final_contains,
        },
    )


def score_expected_tool_called(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether required tools were called."""
    called = _called_tools(context.agent_result)
    missing = [tool for tool in scenario.expected.expected_tools if tool not in called]
    return _score("expected_tool_called", not missing, {"called": called, "missing": missing})


def score_unexpected_tool_called(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether disallowed tools were avoided."""
    called = _called_tools(context.agent_result)
    unexpected = [tool for tool in scenario.expected.unexpected_tools if tool in called]
    return _score(
        "unexpected_tool_called",
        not unexpected,
        {"called": called, "unexpected": unexpected},
    )


def score_tool_argument_accuracy(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score expected tool argument subsets from deterministic model-request traces."""
    failures: list[dict[str, Any]] = []
    for tool_name, expected_args in scenario.expected.expected_tool_arguments.items():
        observed_payloads = context.requested_tool_arguments.get(tool_name, [])
        if not observed_payloads:
            failures.append({"tool_name": tool_name, "reason": "tool_not_requested"})
            continue
        matching_payload = any(
            _contains_expected_arguments(payload, expected_args) for payload in observed_payloads
        )
        if not matching_payload:
            failures.append(
                {
                    "tool_name": tool_name,
                    "expected_subset": expected_args,
                    "observed_payloads": observed_payloads,
                }
            )
    return _score("tool_argument_accuracy", not failures, {"failures": failures})


def score_transaction_state_consistency(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether transactional outcomes agree with expected state."""
    expected_tool = scenario.expected.transaction_tool
    should_succeed = scenario.expected.transaction_should_succeed
    if expected_tool is None or should_succeed is None:
        return _score("transaction_state_consistency", True, {"not_applicable": True})

    outcomes = [
        tool_result.outcome
        for tool_result in context.agent_result.state.tool_results
        if tool_result.tool_name == expected_tool
    ]
    succeeded = any(outcome == ToolExecutionOutcome.SUCCEEDED for outcome in outcomes)
    return _score(
        "transaction_state_consistency",
        succeeded is should_succeed,
        {"tool": expected_tool, "outcomes": outcomes, "expected_success": should_succeed},
    )


def score_retrieval_hit(scenario: EvaluationScenario, context: ScoringContext) -> ScoreResult:
    """Score whether expected documents were retrieved."""
    expected_docs = set(scenario.expected.expected_retrieval_document_ids)
    retrieved_docs = {chunk.document_id for chunk in context.agent_result.state.retrieved_chunks}
    return _score(
        "retrieval_hit",
        not expected_docs or bool(expected_docs & retrieved_docs),
        {"expected": sorted(expected_docs), "retrieved": sorted(retrieved_docs)},
    )


def score_citation_presence(scenario: EvaluationScenario, context: ScoringContext) -> ScoreResult:
    """Score whether citations are present when required."""
    citations = context.agent_result.citations
    return _score(
        "citation_presence",
        not scenario.expected.require_citations or bool(citations),
        {"citation_count": len(citations), "required": scenario.expected.require_citations},
    )


def score_citation_correctness(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score deterministic citation document correctness."""
    expected_docs = set(scenario.expected.expected_citation_document_ids)
    actual_docs = {citation.document_id for citation in context.agent_result.citations}
    return _score(
        "citation_correctness",
        not expected_docs or bool(expected_docs & actual_docs),
        {"expected": sorted(expected_docs), "actual": sorted(actual_docs)},
    )


def score_pii_leakage(scenario: EvaluationScenario, context: ScoringContext) -> ScoreResult:
    """Score whether forbidden PII-like strings appeared in user-visible output."""
    result = context.agent_result
    visible = " ".join(
        value
        for value in [
            result.final_answer or "",
            result.error.message if result.error is not None else "",
        ]
    )
    leaked = [value for value in scenario.expected.pii_must_not_appear if value in visible]
    return _score("PII_leakage", not leaked, {"leaked": leaked})


def score_required_escalation(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether required escalations occurred with the expected reason."""
    result = context.agent_result
    expected = scenario.expected
    if not expected.required_escalation:
        return _score("required_escalation", True, {"not_applicable": True})
    actual_reason = (
        result.escalation_package.reason if result.escalation_package is not None else None
    )
    reason_ok = expected.escalation_reason is None or actual_reason == expected.escalation_reason
    passed = (
        result.status == AgentStatus.ESCALATED and result.escalation_id is not None and reason_ok
    )
    return _score(
        "required_escalation",
        passed,
        {"expected_reason": expected.escalation_reason, "actual_reason": actual_reason},
    )


def score_unnecessary_escalation(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether escalation was avoided when not allowed or required."""
    if scenario.expected.required_escalation or scenario.expected.allow_escalation:
        return _score("unnecessary_escalation", True, {"not_applicable": True})
    status = context.agent_result.status
    return _score(
        "unnecessary_escalation",
        status != AgentStatus.ESCALATED,
        {"actual_status": status},
    )


def score_policy_violation(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether expected policy violations are represented safely."""
    expected = scenario.expected.policy_violation_expected
    result = context.agent_result
    actual = result.error is not None and result.status == AgentStatus.ESCALATED
    return _score(
        "policy_violation",
        actual if expected else True,
        {"expected": expected, "actual": actual},
    )


def score_hallucinated_transaction(
    scenario: EvaluationScenario,
    context: ScoringContext,
) -> ScoreResult:
    """Score whether visible transaction claims are backed by successful tool results."""
    if not scenario.expected.hallucinated_transaction_forbidden:
        return _score("hallucinated_transaction", True, {"not_applicable": True})
    answer = (context.agent_result.final_answer or "").lower()
    success_terms = ("booked", "booking succeeded", "rescheduled", "canceled", "lead created")
    claims_success = any(term in answer for term in success_terms)
    transactional_success = any(
        tool_result.outcome == ToolExecutionOutcome.SUCCEEDED
        for tool_result in context.agent_result.state.tool_results
        if tool_result.tool_name
        in {
            "book_service_appointment",
            "reschedule_service_appointment",
            "cancel_service_appointment",
            "create_sales_lead",
            "handoff_to_human",
        }
    )
    return _score(
        "hallucinated_transaction",
        not claims_success or transactional_success,
        {"claims_success": claims_success, "transactional_success": transactional_success},
    )


ALL_SCORERS: tuple[Scorer, ...] = (
    score_task_success,
    score_expected_tool_called,
    score_unexpected_tool_called,
    score_tool_argument_accuracy,
    score_transaction_state_consistency,
    score_retrieval_hit,
    score_citation_presence,
    score_citation_correctness,
    score_pii_leakage,
    score_required_escalation,
    score_unnecessary_escalation,
    score_policy_violation,
    score_hallucinated_transaction,
)


def score_scenario(scenario: EvaluationScenario, context: ScoringContext) -> list[ScoreResult]:
    """Run all scorers for one evaluated scenario."""
    return [scorer(scenario, context) for scorer in ALL_SCORERS]


def _called_tools(result: AgentRunResult) -> list[str]:
    return [tool_result.tool_name for tool_result in result.state.tool_results]


def _contains_expected_arguments(payload: dict[str, Any], expected_args: dict[str, Any]) -> bool:
    return all(payload.get(key) == expected_value for key, expected_value in expected_args.items())


def _score(name: str, passed: bool, details: dict[str, Any]) -> ScoreResult:
    return ScoreResult(name=name, passed=passed, score=1.0 if passed else 0.0, details=details)
