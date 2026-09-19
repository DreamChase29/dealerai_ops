from collections.abc import Sequence
from datetime import UTC, datetime
from time import sleep
from typing import Any

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dealerai_ops.agents.orchestrator import AgentOrchestrator
from dealerai_ops.agents.providers import FailingLLMProvider, ScriptedLLMProvider
from dealerai_ops.agents.schemas import (
    AgentFailureCode,
    AgentRunRequest,
    AgentStatus,
    ConversationState,
    FinalResponse,
    ModelResponse,
    ToolRequest,
)
from dealerai_ops.db.models import Conversation, ServiceAppointment, ServiceSlot
from dealerai_ops.domain.synthetic import (
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    seed_session,
)
from dealerai_ops.rag.schemas import RetrievedChunk
from dealerai_ops.tools.executor import ToolExecutor
from dealerai_ops.tools.operations import ToolDefinition, ToolRuntime
from dealerai_ops.tools.types import ToolExecutionOutcome, ToolRiskLevel


@pytest.fixture
def seeded_session(session: Session) -> Session:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=80,
            owned_vehicles=100,
            inventory_vehicles=30,
            historical_appointments=250,
            future_service_days=20,
            sales_leads=30,
            conversations=35,
            tool_executions=40,
            escalations=5,
        ),
        seed=654,
        as_of=datetime(2026, 8, 11, 0, 0, tzinfo=UTC),
    )
    seed_session(session, dataset)
    return session


class RepeatingToolProvider:
    def __init__(self, response: ToolRequest) -> None:
        self.response = response

    def next_response(
        self,
        state: ConversationState,
        retrieved_chunks: Sequence[RetrievedChunk],
        tool_metadata: list[dict[str, object]],
    ) -> ModelResponse:
        return self.response


class SlowInput(BaseModel):
    wait_seconds: float = Field(ge=0, le=1)


class SlowOutput(BaseModel):
    ok: bool


def _slow_handler(runtime: ToolRuntime, payload: BaseModel) -> BaseModel:
    request = SlowInput.model_validate(payload)
    sleep(request.wait_seconds)
    return SlowOutput(ok=True)


def _context_ids(session: Session) -> tuple[str, str, str, str]:
    appointment = session.scalars(select(ServiceAppointment).limit(1)).one()
    slot = session.scalars(
        select(ServiceSlot).where(ServiceSlot.booked_count < ServiceSlot.capacity).limit(1)
    ).one()
    conversation = session.scalars(select(Conversation).limit(1)).one()
    return conversation.id, appointment.customer_id, appointment.vehicle_id, slot.id


def _booking_payload(
    customer_id: str,
    vehicle_id: str,
    slot_id: str,
    idempotency_key: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "slot_id": slot_id,
        "appointment_type": "maintenance",
        "channel": "web",
        "confirmed": confirmed,
        "idempotency_key": idempotency_key,
    }


def _request(
    request_id: str,
    conversation_id: str,
    message: str = "help me",
    confirmed: bool = False,
    state: ConversationState | None = None,
) -> AgentRunRequest:
    return AgentRunRequest(
        request_id=request_id,
        conversation_id=conversation_id,
        actor_id="pytest",
        user_message=message,
        confirmed=confirmed,
        state=state,
    )


def test_agent_executes_read_only_tool(seeded_session: Session) -> None:
    conversation_id, customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    provider = ScriptedLLMProvider(
        [
            ToolRequest(tool_name="lookup_customer", arguments={"customer_id": customer_id}),
            FinalResponse(message="I found the synthetic customer record."),
        ]
    )
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    result = orchestrator.run(
        _request(
            "agent-read-0001",
            conversation_id,
            message=f"Look up customer {customer_id}",
        )
    )

    assert result.status == AgentStatus.COMPLETED
    assert result.state.messages[0].metadata["intent"] == "customer_lookup"
    assert result.state.tool_results[0].tool_name == "lookup_customer"
    assert result.state.tool_results[0].outcome == ToolExecutionOutcome.SUCCEEDED


def test_agent_requires_confirmation_before_booking(seeded_session: Session) -> None:
    conversation_id, customer_id, vehicle_id, slot_id = _context_ids(seeded_session)
    slot = seeded_session.get(ServiceSlot, slot_id)
    assert slot is not None
    before = slot.booked_count
    provider = ScriptedLLMProvider(
        [
            ToolRequest(
                tool_name="book_service_appointment",
                arguments=_booking_payload(
                    customer_id,
                    vehicle_id,
                    slot_id,
                    "agent-confirm-0001",
                    confirmed=True,
                ),
            )
        ]
    )
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    result = orchestrator.run(_request("agent-confirm-0001", conversation_id, "Book service"))

    seeded_session.refresh(slot)
    assert result.status == AgentStatus.REQUIRES_CONFIRMATION
    assert result.state.pending_confirmation is not None
    assert result.state.tool_results[0].outcome == ToolExecutionOutcome.REQUIRES_CONFIRMATION
    assert slot.booked_count == before


def test_agent_books_after_confirmation(seeded_session: Session) -> None:
    conversation_id, customer_id, vehicle_id, slot_id = _context_ids(seeded_session)
    slot = seeded_session.get(ServiceSlot, slot_id)
    assert slot is not None
    before = slot.booked_count
    provider = ScriptedLLMProvider(
        [
            ToolRequest(
                tool_name="book_service_appointment",
                arguments=_booking_payload(customer_id, vehicle_id, slot_id, "agent-book-0001"),
            ),
            FinalResponse(message="Appointment booked successfully."),
        ]
    )
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    needs_confirmation = orchestrator.run(_request("agent-book-0001a", conversation_id))
    result = orchestrator.run(
        _request(
            "agent-book-0001b",
            conversation_id,
            message="Yes, confirm booking.",
            confirmed=True,
            state=needs_confirmation.state,
        )
    )

    seeded_session.refresh(slot)
    assert result.status == AgentStatus.COMPLETED
    assert result.final_answer == "Appointment booked successfully."
    assert result.state.tool_results[-1].outcome == ToolExecutionOutcome.SUCCEEDED
    assert slot.booked_count == before + 1


def test_agent_surfaces_failed_booking(seeded_session: Session) -> None:
    conversation_id, _customer_id, vehicle_id, slot_id = _context_ids(seeded_session)
    provider = ScriptedLLMProvider(
        [
            ToolRequest(
                tool_name="book_service_appointment",
                arguments=_booking_payload(
                    "cus_missing",
                    vehicle_id,
                    slot_id,
                    "agent-book-failed-0001",
                ),
            ),
            FinalResponse(message="Booking failed because the customer was not found."),
        ]
    )
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    pending = orchestrator.run(_request("agent-failed-booking-0001a", conversation_id))
    result = orchestrator.run(
        _request(
            "agent-failed-booking-0001b",
            conversation_id,
            message="Yes, confirm the attempted booking.",
            confirmed=True,
            state=pending.state,
        )
    )

    assert result.status == AgentStatus.ESCALATED
    assert result.escalation_id is not None
    assert result.state.tool_results[-1].outcome == ToolExecutionOutcome.FAILED
    assert result.state.tool_results[-1].error is not None
    assert result.state.tool_results[-1].error.message == "Customer not found."


def test_agent_handles_invalid_tool_arguments(seeded_session: Session) -> None:
    conversation_id, _customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    provider = ScriptedLLMProvider(
        [
            ToolRequest(tool_name="lookup_customer", arguments={"unexpected": True}),
            FinalResponse(message="Customer lookup failed due to invalid arguments."),
        ]
    )
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    result = orchestrator.run(_request("agent-invalid-args-0001", conversation_id))

    assert result.status == AgentStatus.COMPLETED
    assert result.state.tool_results[-1].outcome == ToolExecutionOutcome.FAILED
    assert result.state.tool_results[-1].error is not None
    assert result.state.tool_results[-1].error.code == "VALIDATION_ERROR"


def test_agent_rejects_unknown_tool(seeded_session: Session) -> None:
    conversation_id, _customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    provider = ScriptedLLMProvider([ToolRequest(tool_name="write_database_directly", arguments={})])
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    result = orchestrator.run(_request("agent-unknown-tool-0001", conversation_id))

    assert result.status == AgentStatus.FAILED
    assert result.error is not None
    assert result.error.code == AgentFailureCode.UNKNOWN_TOOL


def test_agent_handles_tool_timeout(seeded_session: Session) -> None:
    conversation_id, _customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    slow_tool = ToolDefinition(
        name="slow_lookup",
        description="Synthetic slow read-only tool used for timeout tests.",
        risk_level=ToolRiskLevel.READ_ONLY,
        requires_confirmation=False,
        input_model=SlowInput,
        output_model=SlowOutput,
        handler=_slow_handler,
    )
    provider = ScriptedLLMProvider(
        [ToolRequest(tool_name="slow_lookup", arguments={"wait_seconds": 0.02})]
    )
    orchestrator = AgentOrchestrator(
        provider,
        ToolExecutor(seeded_session, registry={"slow_lookup": slow_tool}),
        tool_timeout_seconds=0.001,
    )

    result = orchestrator.run(_request("agent-tool-timeout-0001", conversation_id))

    assert result.status == AgentStatus.FAILED
    assert result.error is not None
    assert result.error.code == AgentFailureCode.TOOL_TIMEOUT


def test_agent_duplicate_booking_uses_idempotency(seeded_session: Session) -> None:
    conversation_id, customer_id, vehicle_id, slot_id = _context_ids(seeded_session)
    before_appointments = seeded_session.scalar(
        select(func.count()).select_from(ServiceAppointment)
    )
    payload = _booking_payload(customer_id, vehicle_id, slot_id, "agent-duplicate-booking-0001")
    first_orchestrator = AgentOrchestrator(
        ScriptedLLMProvider(
            [
                ToolRequest(tool_name="book_service_appointment", arguments=payload),
                FinalResponse(message="Appointment booked."),
            ]
        ),
        ToolExecutor(seeded_session),
    )
    first_pending = first_orchestrator.run(_request("agent-duplicate-a1", conversation_id))
    first = first_orchestrator.run(
        _request(
            "agent-duplicate-a2",
            conversation_id,
            message="Confirm duplicate booking test.",
            confirmed=True,
            state=first_pending.state,
        )
    )
    second_orchestrator = AgentOrchestrator(
        ScriptedLLMProvider(
            [
                ToolRequest(tool_name="book_service_appointment", arguments=payload),
                FinalResponse(message="Appointment booked."),
            ]
        ),
        ToolExecutor(seeded_session),
    )
    second_pending = second_orchestrator.run(_request("agent-duplicate-b1", conversation_id))
    second = second_orchestrator.run(
        _request(
            "agent-duplicate-b2",
            conversation_id,
            message="Confirm replay booking test.",
            confirmed=True,
            state=second_pending.state,
        )
    )

    assert first.status == AgentStatus.COMPLETED
    assert second.status == AgentStatus.COMPLETED
    assert second.state.tool_results[-1].idempotent_replay is True
    assert (
        seeded_session.scalar(select(func.count()).select_from(ServiceAppointment))
        == before_appointments + 1
    )


def test_agent_handles_provider_failure(seeded_session: Session) -> None:
    conversation_id, _customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    orchestrator = AgentOrchestrator(FailingLLMProvider("offline"), ToolExecutor(seeded_session))

    result = orchestrator.run(_request("agent-provider-failure-0001", conversation_id))

    assert result.status == AgentStatus.ESCALATED
    assert result.error is not None
    assert result.error.code == AgentFailureCode.PROVIDER_FAILURE
    assert result.escalation_id is not None


def test_agent_enforces_iteration_limit(seeded_session: Session) -> None:
    conversation_id, customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    provider = RepeatingToolProvider(
        ToolRequest(tool_name="lookup_customer", arguments={"customer_id": customer_id})
    )
    orchestrator = AgentOrchestrator(
        provider,
        ToolExecutor(seeded_session),
        max_tool_iterations=1,
    )

    result = orchestrator.run(_request("agent-iteration-limit-0001", conversation_id))

    assert result.status == AgentStatus.FAILED
    assert result.error is not None
    assert result.error.code == AgentFailureCode.ITERATION_LIMIT
    assert len(result.state.tool_results) == 1


def test_agent_rejects_fabricated_transaction_success(seeded_session: Session) -> None:
    conversation_id, _customer_id, _vehicle_id, _slot_id = _context_ids(seeded_session)
    provider = ScriptedLLMProvider([FinalResponse(message="Your appointment is booked.")])
    orchestrator = AgentOrchestrator(provider, ToolExecutor(seeded_session))

    result = orchestrator.run(_request("agent-fabricated-success-0001", conversation_id))

    assert result.status == AgentStatus.ESCALATED
    assert result.error is not None
    assert result.error.code == AgentFailureCode.INVALID_MODEL_OUTPUT
    assert result.escalation_id is not None
