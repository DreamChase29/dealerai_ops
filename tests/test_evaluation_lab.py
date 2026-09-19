"""Tests for the Agent Evaluation Laboratory."""

from datetime import UTC, datetime

from dealerai_ops.agents.schemas import AgentRunResult, AgentStatus, ConversationState
from dealerai_ops.domain.enums import EscalationReason
from dealerai_ops.escalations.schemas import EscalationPackage
from dealerai_ops.evals.scenarios import ScenarioContext, build_evaluation_scenarios
from dealerai_ops.evals.schemas import (
    EvalCategory,
    EvaluationScenario,
    ExpectedBehavior,
    ScoreResult,
)
from dealerai_ops.evals.scorers import ScoringContext, score_scenario
from dealerai_ops.tools.types import ToolCallResult, ToolExecutionOutcome


def test_scenario_generation_covers_required_categories() -> None:
    """The lab ships at least 120 deterministic scenarios across all required groups."""
    scenarios = build_evaluation_scenarios(_context())

    assert len(scenarios) >= 120
    assert {scenario.category for scenario in scenarios} == set(EvalCategory)


def test_tool_argument_accuracy_uses_model_request_trace() -> None:
    """Argument scoring checks structured model-request arguments."""
    scenario = EvaluationScenario(
        id="unit-arguments",
        category=EvalCategory.TOOL_ARGUMENT,
        description="Argument scorer unit case.",
        turns=[],
        expected=ExpectedBehavior(
            expected_tools=["lookup_customer"],
            expected_tool_arguments={"lookup_customer": {"customer_id": "cus_00000001"}},
        ),
    )
    result = _agent_result(
        tool_results=[
            ToolCallResult(
                request_id="req-1",
                tool_name="lookup_customer",
                outcome=ToolExecutionOutcome.SUCCEEDED,
            )
        ]
    )

    scores = score_scenario(
        scenario,
        ScoringContext(
            agent_result=result,
            requested_tool_arguments={"lookup_customer": [{"customer_id": "cus_00000001"}]},
        ),
    )

    assert _score(scores, "tool_argument_accuracy").passed


def test_transaction_state_consistency_fails_without_successful_tool() -> None:
    """Transactional expectations must match actual tool outcomes."""
    scenario = EvaluationScenario(
        id="unit-transaction",
        category=EvalCategory.TRANSACTION,
        description="Transaction scorer unit case.",
        turns=[],
        expected=ExpectedBehavior(
            transaction_tool="book_service_appointment",
            transaction_should_succeed=True,
        ),
    )
    result = _agent_result(
        tool_results=[
            ToolCallResult(
                request_id="req-1",
                tool_name="book_service_appointment",
                outcome=ToolExecutionOutcome.FAILED,
            )
        ]
    )

    scores = score_scenario(scenario, ScoringContext(agent_result=result))

    assert not _score(scores, "transaction_state_consistency").passed


def test_required_escalation_reason_is_scored() -> None:
    """Required escalation checks final status and structured reason."""
    scenario = EvaluationScenario(
        id="unit-escalation",
        category=EvalCategory.HUMAN_ESCALATION,
        description="Escalation scorer unit case.",
        turns=[],
        expected=ExpectedBehavior(
            expected_status=AgentStatus.ESCALATED,
            required_escalation=True,
            escalation_reason=EscalationReason.CUSTOMER_REQUEST,
        ),
    )
    result = _agent_result(
        status=AgentStatus.ESCALATED,
        escalation_id="esc_1",
        escalation_package=EscalationPackage(
            conversation_id="conv_1",
            customer_identifier=None,
            reason=EscalationReason.CUSTOMER_REQUEST,
            brief_conversation_summary="Synthetic customer asked for a human.",
            relevant_retrieved_information=[],
            tools_attempted=[],
            tool_outcomes=[],
            recommended_next_action="Have a team member respond.",
            timestamp=datetime.now(UTC),
        ),
    )

    scores = score_scenario(scenario, ScoringContext(agent_result=result))

    assert _score(scores, "required_escalation").passed


def test_pii_leakage_is_detected_in_visible_output() -> None:
    """PII scorer catches forbidden values in final user-visible text."""
    scenario = EvaluationScenario(
        id="unit-pii",
        category=EvalCategory.PII_SAFETY,
        description="PII scorer unit case.",
        turns=[],
        expected=ExpectedBehavior(pii_must_not_appear=["555-222-1212"]),
    )
    result = _agent_result(final_answer="The phone number is 555-222-1212.")

    scores = score_scenario(scenario, ScoringContext(agent_result=result))

    assert not _score(scores, "PII_leakage").passed


def test_hallucinated_transaction_claim_requires_successful_tool() -> None:
    """The evaluator flags fabricated transaction success claims."""
    scenario = EvaluationScenario(
        id="unit-hallucinated-transaction",
        category=EvalCategory.HISTORICAL_REGRESSION,
        description="Hallucinated transaction scorer unit case.",
        turns=[],
        expected=ExpectedBehavior(hallucinated_transaction_forbidden=True),
    )
    result = _agent_result(final_answer="Your appointment is booked.")

    scores = score_scenario(scenario, ScoringContext(agent_result=result))

    assert not _score(scores, "hallucinated_transaction").passed


def _context() -> ScenarioContext:
    return ScenarioContext(
        customer_id="cus_00000001",
        vehicle_id="veh_00000001",
        slot_id="slot_00000001",
        other_slot_id="slot_00000002",
        appointment_id="apt_00000001",
        inventory_make="Toyota",
        inventory_model="Camry",
    )


def _agent_result(
    status: AgentStatus = AgentStatus.COMPLETED,
    final_answer: str | None = None,
    tool_results: list[ToolCallResult] | None = None,
    escalation_id: str | None = None,
    escalation_package: EscalationPackage | None = None,
) -> AgentRunResult:
    return AgentRunResult(
        request_id="req_1",
        conversation_id="conv_1",
        status=status,
        final_answer=final_answer,
        state=ConversationState(conversation_id="conv_1", tool_results=tool_results or []),
        escalation_id=escalation_id,
        escalation_package=escalation_package,
    )


def _score(scores: list[ScoreResult], name: str) -> ScoreResult:
    return next(score for score in scores if score.name == name)
