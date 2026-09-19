"""Core types for deterministic typed tool execution."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ToolRiskLevel(StrEnum):
    """Risk classes for agent-callable operational tools."""

    READ_ONLY = "READ_ONLY"
    LOW_RISK_WRITE = "LOW_RISK_WRITE"
    HIGH_RISK_WRITE = "HIGH_RISK_WRITE"
    ESCALATION = "ESCALATION"


class ToolExecutionOutcome(StrEnum):
    """Framework-level tool execution outcomes."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    UNAUTHORIZED = "unauthorized"


class ToolMetadata(BaseModel):
    """Metadata exposed to future agent planners and evaluators."""

    name: str
    description: str
    risk_level: ToolRiskLevel
    requires_confirmation: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolContext(BaseModel):
    """Execution context supplied by API, future agent runtime, or tests."""

    request_id: str = Field(min_length=1, max_length=80)
    actor_id: str = Field(default="system", min_length=1, max_length=80)
    scopes: frozenset[str] = Field(default_factory=frozenset)
    conversation_id: str | None = None

    model_config = ConfigDict(frozen=True)


class ToolError(BaseModel):
    """Structured deterministic tool error."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """Envelope returned by every tool execution."""

    request_id: str
    tool_name: str
    outcome: ToolExecutionOutcome
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    idempotent_replay: bool = False


class AuthorizationDecision(BaseModel):
    """Authorization hook result."""

    allowed: bool
    reason: str | None = None


class ToolAuthorizer(Protocol):
    """Authorization hook interface for tool execution."""

    def authorize(
        self,
        context: ToolContext,
        metadata: ToolMetadata,
        payload: Mapping[str, Any],
    ) -> AuthorizationDecision:
        """Return whether a tool call is authorized."""


class AllowAllAuthorizer:
    """Default local-mode authorizer used by tests and deterministic development."""

    def authorize(
        self,
        context: ToolContext,
        metadata: ToolMetadata,
        payload: Mapping[str, Any],
    ) -> AuthorizationDecision:
        """Allow all calls."""
        return AuthorizationDecision(allowed=True)
