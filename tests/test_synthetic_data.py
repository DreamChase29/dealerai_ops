from collections import Counter
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dealerai_ops.db.models import Customer, ServiceAppointment, ServiceHistory, Vehicle
from dealerai_ops.domain.enums import AppointmentChannel, AppointmentStatus, AppointmentType
from dealerai_ops.domain.synthetic import (
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    ids_are_unique,
    seed_session,
)


def test_default_synthetic_dataset_meets_required_minimum_counts() -> None:
    dataset = generate_synthetic_dataset()
    summary = dataset.summary()

    assert summary["customers"] >= 2_000
    assert summary["vehicles"] >= 2_500
    assert summary["inventory_vehicles"] >= 300
    assert summary["service_appointments"] >= 5_000
    assert summary["service_history"] > 0
    assert summary["service_slots"] > 0
    assert summary["sales_leads"] > 0


def test_synthetic_generation_is_deterministic() -> None:
    counts = SyntheticDatasetCounts(
        customers=30,
        owned_vehicles=40,
        inventory_vehicles=12,
        historical_appointments=90,
        future_service_days=8,
        sales_leads=20,
        conversations=24,
        tool_executions=30,
        escalations=5,
    )

    first = generate_synthetic_dataset(counts=counts, seed=123)
    second = generate_synthetic_dataset(counts=counts, seed=123)

    assert first.summary() == second.summary()
    assert [customer.email_hash for customer in first.customers[:10]] == [
        customer.email_hash for customer in second.customers[:10]
    ]
    assert [appointment.status for appointment in first.service_appointments[:25]] == [
        appointment.status for appointment in second.service_appointments[:25]
    ]


def test_generated_identifiers_are_unique() -> None:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=40,
            owned_vehicles=50,
            inventory_vehicles=20,
            historical_appointments=125,
            future_service_days=7,
            sales_leads=30,
            conversations=30,
            tool_executions=40,
            escalations=6,
        ),
    )

    assert ids_are_unique(dataset.all_records())
    assert len({vehicle.vin for vehicle in dataset.vehicles}) == len(dataset.vehicles)
    assert len({vehicle.vin for vehicle in dataset.inventory_vehicles}) == len(
        dataset.inventory_vehicles,
    )


def test_generated_appointments_have_valid_states_and_dates() -> None:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=40,
            owned_vehicles=50,
            inventory_vehicles=20,
            historical_appointments=150,
            future_service_days=7,
            sales_leads=30,
            conversations=30,
            tool_executions=40,
            escalations=6,
        ),
    )
    valid_statuses = set(AppointmentStatus)
    history_by_appointment = {record.appointment_id for record in dataset.service_history}
    completed_appointments = {
        appointment.id
        for appointment in dataset.service_appointments
        if appointment.status == AppointmentStatus.COMPLETED
    }

    for appointment in dataset.service_appointments:
        assert appointment.status in valid_statuses
        assert appointment.booked_at <= appointment.scheduled_start_at
        assert appointment.scheduled_start_at < appointment.scheduled_end_at
        assert appointment.lead_time_days >= 0
        assert appointment.reminder_count >= 0
        if appointment.confirmed_at is not None:
            assert appointment.confirmed_at <= appointment.scheduled_start_at
        if appointment.canceled_at is not None:
            assert (
                appointment.booked_at <= appointment.canceled_at <= appointment.scheduled_start_at
            )
        if appointment.completed_at is not None:
            assert appointment.completed_at == appointment.scheduled_end_at

    assert history_by_appointment == completed_appointments


def test_generated_records_preserve_referential_integrity(session: Session) -> None:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=30,
            owned_vehicles=40,
            inventory_vehicles=10,
            historical_appointments=100,
            future_service_days=5,
            sales_leads=15,
            conversations=20,
            tool_executions=25,
            escalations=4,
        ),
        seed=456,
    )

    summary = seed_session(session, dataset)

    assert session.scalar(select(func.count()).select_from(Customer)) == summary["customers"]
    assert session.scalar(select(func.count()).select_from(Vehicle)) == summary["vehicles"]
    assert (
        session.scalar(select(func.count()).select_from(ServiceAppointment))
        == summary["service_appointments"]
    )
    assert (
        session.scalar(select(func.count()).select_from(ServiceHistory))
        == summary["service_history"]
    )


def test_database_rejects_orphan_appointments(session: Session) -> None:
    appointment = ServiceAppointment(
        id="apt_orphan",
        customer_id="cus_missing",
        vehicle_id="veh_missing",
        slot_id=None,
        status=AppointmentStatus.SCHEDULED,
        appointment_type=AppointmentType.MAINTENANCE,
        channel=AppointmentChannel.WEB,
        scheduled_start_at=datetime(2026, 1, 20, 9, 0, tzinfo=UTC),
        scheduled_end_at=datetime(2026, 1, 20, 10, 0, tzinfo=UTC),
        booked_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
        confirmed_at=None,
        canceled_at=None,
        completed_at=None,
        lead_time_days=10,
        estimated_duration_minutes=60,
        is_first_service_visit=True,
        prior_no_show_count_at_booking=0,
        reminder_count=1,
        advisor_id="adv_001",
        created_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
    )

    session.add(appointment)
    with pytest.raises(IntegrityError):
        session.flush()


def test_customer_behavior_features_do_not_include_protected_class_fields() -> None:
    forbidden = {"race", "ethnicity", "gender", "sex", "religion", "date_of_birth", "age"}
    customer_columns = set(Customer.__table__.columns.keys())

    assert customer_columns.isdisjoint(forbidden)


def test_status_distribution_contains_no_show_signal() -> None:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=80,
            owned_vehicles=100,
            inventory_vehicles=20,
            historical_appointments=500,
            future_service_days=7,
            sales_leads=30,
            conversations=40,
            tool_executions=50,
            escalations=6,
        ),
        seed=789,
    )
    status_counts = Counter(appointment.status for appointment in dataset.service_appointments)

    assert status_counts[AppointmentStatus.NO_SHOW] > 0
    assert status_counts[AppointmentStatus.COMPLETED] > status_counts[AppointmentStatus.NO_SHOW]
