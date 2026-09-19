"""Schemas for the Agent Evaluation Laboratory."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dealerai_ops.agents.schemas import AgentRunResult, AgentStatus, ModelResponse
from dealerai_ops.domain.enums import EscalationReason


class EvalCategory(StrEnum):
    """Scenario categories covered by the laboratory."""

    NORMAL_CUSTOMER = "normal_customer"
    MULTI_TURN = "multi_turn"
    TOOL_SELECTION = "tool_selection"
    TOOL_ARGUMENT = "tool_argument"
    RAG = "rag"
    TRANSACTION = "transaction"
    TOOL_FAILURE = "tool_failure"
    HUMAN_ESCALATION = "human_escalation"
    PII_SAFETY = "pii_safety"
    PROMPT_INJECTION = "prompt_injection"
    HISTORICAL_REGRESSION = "historical_regression"


class EvalTurn(BaseModel):
    """One user turn and deterministic provider script."""

    model_config = ConfigDict(extra="forbid")

    user_message: str
    model_responses: list[ModelResponse] = Field(default_factory=list)
    confirmed: bool = False
    authenticated_customer_id: str | None = None


class ExpectedBehavior(BaseModel):
    """Expected behavior used by programmatic scorers."""

    model_config = ConfigDict(extra="forbid")

    expected_status: AgentStatus | None = None
    expected_tools: list[str] = Field(default_factory=list)
    unexpected_tools: list[str] = Field(default_factory=list)
    expected_tool_arguments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    expected_retrieval_document_ids: list[str] = Field(default_factory=list)
    require_citations: bool = False
    expected_citation_document_ids: list[str] = Field(default_factory=list)
    pii_must_not_appear: list[str] = Field(default_factory=list)
    required_escalation: bool = False
    escalation_reason: EscalationReason | None = None
    allow_escalation: bool = True
    transaction_tool: str | None = None
    transaction_should_succeed: bool | None = None
    policy_violation_expected: bool = False
    hallucinated_transaction_forbidden: bool = True
    expected_final_contains: list[str] = Field(default_factory=list)


class EvaluationScenario(BaseModel):
    """Complete deterministic evaluation scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: EvalCategory
    description: str
    turns: list[EvalTurn]
    expected: ExpectedBehavior
    tags: list[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    """One scorer result."""

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    score: float
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionMetadata(BaseModel):
    """Operational metadata captured during one scenario run."""

    model_config = ConfigDict(extra="forbid")

    latency_ms: float
    model_calls: int
    tool_calls: int
    retrieval_count: int
    token_metadata: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    requested_tool_arguments: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """One evaluated scenario result."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    scenario_id: str
    category: EvalCategory
    description: str
    passed: bool
    scores: list[ScoreResult]
    metadata: ExecutionMetadata
    final_status: AgentStatus
    final_answer: str | None = None
    escalation_id: str | None = None
    error_code: str | None = None
    agent_result: AgentRunResult


class AggregateMetrics(BaseModel):
    """Aggregate evaluation metrics."""

    model_config = ConfigDict(extra="forbid")

    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    pass_rate: float
    category_pass_rate: dict[str, float]
    scorer_pass_rate: dict[str, float]
    average_latency_ms: float
    total_model_calls: int
    total_tool_calls: int
    total_retrieval_count: int
    estimated_cost_usd: float


class EvaluationRunReport(BaseModel):
    """Complete evaluation run report."""

    model_config = ConfigDict(extra="forbid")

    generated_at: str
    aggregate_metrics: AggregateMetrics
    results: list[EvaluationResult]
