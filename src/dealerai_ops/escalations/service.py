"""Services for creating and retrieving human escalation packages."""

import hashlib
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from dealerai_ops.agents.schemas import ConversationState
from dealerai_ops.core.redaction import redact_text
from dealerai_ops.db.models import Conversation, Escalation
from dealerai_ops.domain.enums import ConversationStatus, EscalationReason, EscalationStatus
from dealerai_ops.domain.repositories import ConversationRepository, EscalationRepository
from dealerai_ops.escalations.schemas import (
    EscalationPackage,
    EscalationRecord,
    RetrievedInfoSummary,
    ToolOutcomeSummary,
)

MAX_SUMMARY_CHARS = 500
MAX_RETRIEVED_EXCERPT_CHARS = 260


class EscalationService:
    """Create and retrieve structured escalation records."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.escalations = EscalationRepository(session)

    def create_escalation_package(
        self,
        request_id: str,
        conversation_id: str,
        reason: EscalationReason,
        state: ConversationState,
        recommended_next_action: str,
        authenticated_customer_id: str | None = None,
        assigned_team: str = "customer_care",
        severity: str = "medium",
        timestamp: datetime | None = None,
    ) -> EscalationRecord:
        """Create and persist a redacted human escalation package."""
        created_at = timestamp or datetime.now(UTC)
        conversation = self._ensure_conversation(
            conversation_id=conversation_id,
            customer_id=authenticated_customer_id,
            reason=reason,
            created_at=created_at,
        )
        package = EscalationPackage(
            conversation_id=conversation.id,
            customer_identifier=authenticated_customer_id,
            reason=reason,
            brief_conversation_summary=_summarize_conversation(state),
            relevant_retrieved_information=[
                RetrievedInfoSummary(
                    document_id=chunk.document_id,
                    title=chunk.title,
                    section=chunk.section,
                    chunk_id=chunk.chunk_id,
                    score=chunk.score,
                    excerpt=_truncate(redact_text(chunk.text), MAX_RETRIEVED_EXCERPT_CHARS),
                )
                for chunk in state.retrieved_chunks
            ],
            tools_attempted=list(dict.fromkeys(result.tool_name for result in state.tool_results)),
            tool_outcomes=[
                ToolOutcomeSummary(
                    tool_name=result.tool_name,
                    outcome=result.outcome.value,
                    error_code=result.error.code if result.error else None,
                    error_message=redact_text(result.error.message) if result.error else None,
                )
                for result in state.tool_results
            ],
            recommended_next_action=recommended_next_action,
            timestamp=created_at,
        )
        escalation = Escalation(
            id=_stable_id("esc", f"{request_id}:{reason.value}"),
            conversation_id=conversation.id,
            customer_id=authenticated_customer_id,
            reason_code=reason.value,
            severity=severity,
            status=EscalationStatus.OPEN,
            assigned_team=assigned_team,
            package_payload=package.model_dump(mode="json"),
            created_at=created_at,
            resolved_at=None,
        )
        existing = self.escalations.get(escalation.id)
        if existing is None:
            self.escalations.add(escalation)
            self.session.commit()
            return self.to_record(escalation)
        return self.to_record(existing)

    def list_escalations(self, limit: int = 100, offset: int = 0) -> list[EscalationRecord]:
        """Return escalation records for the demo API."""
        return [self.to_record(escalation) for escalation in self.escalations.list(limit, offset)]

    def get_escalation(self, escalation_id: str) -> EscalationRecord | None:
        """Return one escalation record by ID."""
        escalation = self.escalations.get(escalation_id)
        return self.to_record(escalation) if escalation is not None else None

    def to_record(self, escalation: Escalation) -> EscalationRecord:
        """Convert an ORM escalation to its public package response."""
        reason = _reason_from_code(escalation.reason_code)
        try:
            package = EscalationPackage.model_validate(escalation.package_payload)
        except ValidationError:
            package = EscalationPackage(
                conversation_id=escalation.conversation_id,
                customer_identifier=escalation.customer_id,
                reason=reason,
                brief_conversation_summary="Synthetic legacy escalation record.",
                recommended_next_action="Review the synthetic escalation record.",
                timestamp=escalation.created_at,
            )
        return EscalationRecord(
            id=escalation.id,
            conversation_id=escalation.conversation_id,
            customer_identifier=package.customer_identifier,
            reason=reason,
            severity=escalation.severity,
            status=escalation.status,
            assigned_team=escalation.assigned_team,
            package=package,
            created_at=escalation.created_at,
        )

    def _ensure_conversation(
        self,
        conversation_id: str,
        customer_id: str | None,
        reason: EscalationReason,
        created_at: datetime,
    ) -> Conversation:
        conversation = self.conversations.get(conversation_id)
        if conversation is not None:
            conversation.status = ConversationStatus.ESCALATED
            self.session.flush()
            return conversation
        conversation = Conversation(
            id=conversation_id,
            customer_id=customer_id,
            sales_lead_id=None,
            channel="agent",
            status=ConversationStatus.ESCALATED,
            intent="human_escalation",
            started_at=created_at,
            ended_at=None,
            metadata_={"escalation_reason": reason.value},
            created_at=created_at,
        )
        return self.conversations.add(conversation)


def _summarize_conversation(state: ConversationState) -> str:
    snippets = []
    for message in state.messages[-6:]:
        snippets.append(f"{message.role.value}: {_truncate(redact_text(message.content), 120)}")
    if not snippets:
        return "No conversation messages were available."
    return _truncate(" | ".join(snippets), MAX_SUMMARY_CHARS)


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3]}..."


def _stable_id(prefix: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _reason_from_code(reason_code: str) -> EscalationReason:
    try:
        return EscalationReason(reason_code)
    except ValueError:
        if reason_code == "safety_concern":
            return EscalationReason.SAFETY_CONCERN
        if reason_code in {"policy_exception", "payment_dispute"}:
            return EscalationReason.POLICY_RESTRICTION
        return EscalationReason.CUSTOMER_REQUEST
