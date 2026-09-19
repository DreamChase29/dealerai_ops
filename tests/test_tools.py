from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dealerai_ops.db.models import (
    Escalation,
    SalesLead,
    ServiceAppointment,
    ServiceSlot,
    ToolExecution,
    ToolIdempotencyRecord,
)
from dealerai_ops.domain.enums import AppointmentStatus, ToolExecutionStatus
from dealerai_ops.domain.synthetic import (
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    seed_session,
)
from dealerai_ops.ml.schemas import NoShowPredictionRequest, NoShowPredictionResponse, RiskTier
from dealerai_ops.tools.executor import ToolExecutor
from dealerai_ops.tools.operations import build_tool_registry
from dealerai_ops.tools.types import (
    AuthorizationDecision,
    ToolContext,
    ToolExecutionOutcome,
    ToolMetadata,
    ToolRiskLevel,
)


class DenyHighRiskAuthorizer:
    def authorize(
        self,
        context: ToolContext,
        metadata: ToolMetadata,
        payload: Mapping[str, Any],
    ) -> AuthorizationDecision:
        if metadata.risk_level == ToolRiskLevel.HIGH_RISK_WRITE:
            return AuthorizationDecision(allowed=False, reason="high risk writes disabled")
        return AuthorizationDecision(allowed=True)


class FakeNoShowService:
    def predict(self, request: NoShowPredictionRequest) -> NoShowPredictionResponse:
        return NoShowPredictionResponse(
            probability=0.42,
            risk_tier=RiskTier.VERY_HIGH,
            model_version="fake-v1",
        )


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
        seed=987,
        as_of=datetime(2026, 8, 11, 0, 0, tzinfo=UTC),
    )
    seed_session(session, dataset)
    return session


def _context(index: int) -> ToolContext:
    return ToolContext(request_id=f"tool-test-request-{index:04d}", actor_id="pytest")


def _first_customer_vehicle_slot(session: Session) -> tuple[str, str, str, str]:
    appointment = session.scalars(select(ServiceAppointment).limit(1)).one()
    slot = session.scalars(
        select(ServiceSlot).where(ServiceSlot.booked_count < ServiceSlot.capacity).limit(1)
    ).one()
    other_slot = session.scalars(
        select(ServiceSlot)
        .where(
            ServiceSlot.booked_count < ServiceSlot.capacity,
            ServiceSlot.id != slot.id,
        )
        .limit(1)
    ).one()
    return appointment.customer_id, appointment.vehicle_id, slot.id, other_slot.id


def _booking_payload(
    customer_id: str,
    vehicle_id: str,
    slot_id: str,
    key: str,
    confirmed: bool = True,
) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "slot_id": slot_id,
        "appointment_type": "maintenance",
        "channel": "web",
        "confirmed": confirmed,
        "idempotency_key": key,
    }


def test_all_tools_expose_required_metadata() -> None:
    registry = build_tool_registry()
    expected = {
        "lookup_customer",
        "get_customer_vehicle",
        "get_service_history",
        "search_inventory",
        "get_vehicle_details",
        "get_available_service_slots",
        "predict_no_show_risk",
        "book_service_appointment",
        "reschedule_service_appointment",
        "cancel_service_appointment",
        "create_sales_lead",
        "handoff_to_human",
    }

    assert set(registry) == expected
    for definition in registry.values():
        metadata = definition.metadata
        assert metadata.name
        assert metadata.description
        assert metadata.risk_level in set(ToolRiskLevel)
        assert isinstance(metadata.requires_confirmation, bool)
        assert metadata.input_schema
        assert metadata.output_schema


def test_tool_validation_error_is_structured_and_audited(seeded_session: Session) -> None:
    executor = ToolExecutor(seeded_session)

    result = executor.execute(
        "lookup_customer",
        {"customer_id": "cus_00000001", "unexpected": True},
        _context(1),
    )

    assert result.outcome == ToolExecutionOutcome.FAILED
    assert result.error is not None
    assert result.error.code == "VALIDATION_ERROR"
    audit = seeded_session.scalar(
        select(ToolExecution).where(ToolExecution.request_id == "tool-test-request-0001")
    )
    assert audit is not None
    assert audit.status == ToolExecutionStatus.FAILED


def test_authorization_denial_prevents_high_risk_write(seeded_session: Session) -> None:
    customer_id, vehicle_id, slot_id, _other_slot_id = _first_customer_vehicle_slot(seeded_session)
    slot_before = seeded_session.get(ServiceSlot, slot_id)
    assert slot_before is not None
    original_booked_count = slot_before.booked_count
    executor = ToolExecutor(seeded_session, authorizer=DenyHighRiskAuthorizer())

    result = executor.execute(
        "book_service_appointment",
        _booking_payload(customer_id, vehicle_id, slot_id, "booking-auth-denied-0001"),
        _context(2),
    )

    seeded_session.refresh(slot_before)
    assert result.outcome == ToolExecutionOutcome.UNAUTHORIZED
    assert slot_before.booked_count == original_booked_count
    assert result.error is not None
    assert result.error.message == "high risk writes disabled"


def test_read_only_tools_execute_deterministically_and_audit(seeded_session: Session) -> None:
    executor = ToolExecutor(seeded_session, no_show_service=FakeNoShowService())
    appointment = seeded_session.scalars(select(ServiceAppointment).limit(1)).one()

    calls = [
        ("lookup_customer", {"customer_id": appointment.customer_id}),
        (
            "get_customer_vehicle",
            {"customer_id": appointment.customer_id, "vehicle_id": appointment.vehicle_id},
        ),
        ("get_service_history", {"vehicle_id": appointment.vehicle_id, "limit": 5}),
        ("search_inventory", {"limit": 5}),
        ("get_vehicle_details", {"vehicle_id": appointment.vehicle_id}),
        ("get_available_service_slots", {"limit": 3}),
        ("predict_no_show_risk", {"appointment_id": appointment.id}),
    ]

    for index, (tool_name, payload) in enumerate(calls, start=10):
        result = executor.execute(tool_name, payload, _context(index))
        assert result.outcome == ToolExecutionOutcome.SUCCEEDED
        assert result.data is not None

    prediction = executor.execute(
        "predict_no_show_risk",
        {"appointment_id": appointment.id},
        _context(30),
    )
    assert prediction.data == {
        "probability": 0.42,
        "risk_tier": "VERY_HIGH",
        "model_version": "fake-v1",
    }
    audited = seeded_session.scalar(
        select(func.count())
        .select_from(ToolExecution)
        .where(ToolExecution.request_id.like("tool-test%"))
    )
    assert audited == 8


def test_confirmation_required_blocks_booking_without_mutation(seeded_session: Session) -> None:
    customer_id, vehicle_id, slot_id, _other_slot_id = _first_customer_vehicle_slot(seeded_session)
    slot = seeded_session.get(ServiceSlot, slot_id)
    assert slot is not None
    before = slot.booked_count
    executor = ToolExecutor(seeded_session)

    result = executor.execute(
        "book_service_appointment",
        _booking_payload(customer_id, vehicle_id, slot_id, "booking-needs-confirm-0001", False),
        _context(40),
    )

    seeded_session.refresh(slot)
    assert result.outcome == ToolExecutionOutcome.REQUIRES_CONFIRMATION
    assert slot.booked_count == before
    assert seeded_session.scalar(select(func.count()).select_from(ToolIdempotencyRecord)) == 0


def test_booking_is_transactional_and_idempotent(seeded_session: Session) -> None:
    customer_id, vehicle_id, slot_id, _other_slot_id = _first_customer_vehicle_slot(seeded_session)
    slot = seeded_session.get(ServiceSlot, slot_id)
    assert slot is not None
    before_slot_count = slot.booked_count
    before_appointments = seeded_session.scalar(
        select(func.count()).select_from(ServiceAppointment)
    )
    executor = ToolExecutor(seeded_session)
    payload = _booking_payload(customer_id, vehicle_id, slot_id, "booking-idem-key-0001")

    first = executor.execute("book_service_appointment", payload, _context(50))
    second = executor.execute("book_service_appointment", payload, _context(51))

    seeded_session.refresh(slot)
    assert first.outcome == ToolExecutionOutcome.SUCCEEDED
    assert second.outcome == ToolExecutionOutcome.SUCCEEDED
    assert second.idempotent_replay is True
    assert first.data == second.data
    assert slot.booked_count == before_slot_count + 1
    assert (
        seeded_session.scalar(select(func.count()).select_from(ServiceAppointment))
        == before_appointments + 1
    )
    assert seeded_session.scalar(select(func.count()).select_from(ToolIdempotencyRecord)) == 1
    assert (
        seeded_session.scalar(
            select(func.count())
            .select_from(ToolExecution)
            .where(ToolExecution.idempotency_key == "booking-idem-key-0001")
        )
        == 2
    )


def test_idempotency_conflict_does_not_create_second_booking(seeded_session: Session) -> None:
    customer_id, vehicle_id, slot_id, other_slot_id = _first_customer_vehicle_slot(seeded_session)
    before_appointments = seeded_session.scalar(
        select(func.count()).select_from(ServiceAppointment)
    )
    executor = ToolExecutor(seeded_session)
    first_payload = _booking_payload(customer_id, vehicle_id, slot_id, "booking-conflict-0001")
    second_payload = _booking_payload(
        customer_id, vehicle_id, other_slot_id, "booking-conflict-0001"
    )

    first = executor.execute("book_service_appointment", first_payload, _context(60))
    second = executor.execute("book_service_appointment", second_payload, _context(61))

    assert first.outcome == ToolExecutionOutcome.SUCCEEDED
    assert second.outcome == ToolExecutionOutcome.FAILED
    assert second.error is not None
    assert second.error.code == "IDEMPOTENCY_CONFLICT"
    assert (
        seeded_session.scalar(select(func.count()).select_from(ServiceAppointment))
        == before_appointments + 1
    )


def test_reschedule_and_cancel_are_confirmed_transactional_writes(seeded_session: Session) -> None:
    customer_id, vehicle_id, slot_id, other_slot_id = _first_customer_vehicle_slot(seeded_session)
    executor = ToolExecutor(seeded_session)
    booked = executor.execute(
        "book_service_appointment",
        _booking_payload(customer_id, vehicle_id, slot_id, "booking-reschedule-0001"),
        _context(70),
    )
    assert booked.data is not None
    appointment_id = booked.data["appointment"]["id"]

    rescheduled = executor.execute(
        "reschedule_service_appointment",
        {
            "appointment_id": appointment_id,
            "new_slot_id": other_slot_id,
            "confirmed": True,
            "idempotency_key": "reschedule-idem-0001",
        },
        _context(71),
    )
    canceled = executor.execute(
        "cancel_service_appointment",
        {
            "appointment_id": appointment_id,
            "confirmed": True,
            "idempotency_key": "cancel-idem-0001",
        },
        _context(72),
    )

    appointment = seeded_session.get(ServiceAppointment, appointment_id)
    assert rescheduled.outcome == ToolExecutionOutcome.SUCCEEDED
    assert canceled.outcome == ToolExecutionOutcome.SUCCEEDED
    assert appointment is not None
    assert appointment.status == AppointmentStatus.CANCELED


def test_create_sales_lead_and_handoff_to_human(seeded_session: Session) -> None:
    appointment = seeded_session.scalars(select(ServiceAppointment).limit(1)).one()
    executor = ToolExecutor(seeded_session)

    lead_result = executor.execute(
        "create_sales_lead",
        {
            "source": "website",
            "desired_make": "Toyota",
            "desired_model": "RAV4",
            "budget_min": "25000.00",
            "budget_max": "42000.00",
            "customer_id": appointment.customer_id,
            "confirmed": True,
            "idempotency_key": "lead-idem-0001",
        },
        _context(80),
    )
    handoff_result = executor.execute(
        "handoff_to_human",
        {
            "reason_code": "complex_repair",
            "severity": "medium",
            "assigned_team": "service_manager",
            "customer_id": appointment.customer_id,
            "idempotency_key": "handoff-idem-0001",
        },
        _context(81),
    )

    assert lead_result.outcome == ToolExecutionOutcome.SUCCEEDED
    assert handoff_result.outcome == ToolExecutionOutcome.SUCCEEDED
    assert seeded_session.scalar(select(func.count()).select_from(SalesLead)) >= 31
    assert seeded_session.scalar(select(func.count()).select_from(Escalation)) >= 6
