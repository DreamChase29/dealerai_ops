"""Schemas for provider-independent agent orchestration."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dealerai_ops.escalations.schemas import EscalationPackage
from dealerai_ops.rag.schemas import Citation, RetrievedChunk
from dealerai_ops.tools.types import ToolCallResult


class AgentRole(StrEnum):
    """Conversation message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class AgentStatus(StrEnum):
    """Agent run status."""

    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    ESCALATED = "escalated"


class AgentFailureCode(StrEnum):
    """Structured agent failure codes."""

    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    ITERATION_LIMIT = "ITERATION_LIMIT"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class AgentMessage(BaseModel):
    """Explicit conversation message state."""

    model_config = ConfigDict(extra="forbid")

    role: AgentRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolRequest(BaseModel):
    """Structured model request to call a registered tool."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_request"] = "tool_request"
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class FinalResponse(BaseModel):
    """Structured model final response."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["final"] = "final"
    message: str


ModelResponse = ToolRequest | FinalResponse


class ConversationState(BaseModel):
    """State maintained across an agent run."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    messages: list[AgentMessage] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    tool_results: list[ToolCallResult] = Field(default_factory=list)
    iteration_count: int = 0
    pending_confirmation: ToolRequest | None = None


class AgentRunRequest(BaseModel):
    """Input to the agent orchestrator."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=80)
    user_message: str = Field(min_length=1)
    actor_id: str = Field(default="system", min_length=1, max_length=80)
    conversation_id: str = Field(min_length=1, max_length=80)
    authenticated_customer_id: str | None = Field(default=None, max_length=32)
    confirmed: bool = False
    state: ConversationState | None = None


class AgentError(BaseModel):
    """Structured agent failure."""

    model_config = ConfigDict(extra="forbid")

    code: AgentFailureCode | str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    """Structured result from one agent run."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    conversation_id: str
    status: AgentStatus
    final_answer: str | None = None
    state: ConversationState
    error: AgentError | None = None
    citations: list[Citation] = Field(default_factory=list)
    escalation_id: str | None = None
    escalation_package: EscalationPackage | None = None
