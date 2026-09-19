"""Schemas for human escalation packages."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from dealerai_ops.domain.enums import EscalationReason, EscalationStatus


class RetrievedInfoSummary(BaseModel):
    """Redacted retrieved information included in an escalation package."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    section: str
    chunk_id: str
    score: float
    excerpt: str


class ToolOutcomeSummary(BaseModel):
    """Tool execution summary suitable for human review."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    outcome: str
    error_code: str | None = None
    error_message: str | None = None


class EscalationPackage(BaseModel):
    """Structured handoff package for dealership staff."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    customer_identifier: str | None = None
    reason: EscalationReason
    brief_conversation_summary: str
    relevant_retrieved_information: list[RetrievedInfoSummary] = Field(default_factory=list)
    tools_attempted: list[str] = Field(default_factory=list)
    tool_outcomes: list[ToolOutcomeSummary] = Field(default_factory=list)
    recommended_next_action: str
    timestamp: datetime


class EscalationRecord(BaseModel):
    """Public demo API representation of an escalation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    customer_identifier: str | None = None
    reason: EscalationReason
    severity: str
    status: EscalationStatus
    assigned_team: str
    package: EscalationPackage
    created_at: datetime


class EscalationListResponse(BaseModel):
    """Paginated escalation list response."""

    model_config = ConfigDict(extra="forbid")

    escalations: list[EscalationRecord]
    limit: int
    offset: int
