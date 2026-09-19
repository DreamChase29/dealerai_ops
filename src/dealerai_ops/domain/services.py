"""Domain services built on repository abstractions."""

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from dealerai_ops.db.models import (
    Conversation,
    Customer,
    Escalation,
    InventoryVehicle,
    SalesLead,
    ServiceAppointment,
    ServiceHistory,
    ServiceSlot,
    Vehicle,
)
from dealerai_ops.domain.enums import (
    AppointmentChannel,
    AppointmentStatus,
    AppointmentType,
    ConversationStatus,
    EscalationStatus,
    LeadStatus,
)
from dealerai_ops.domain.repositories import (
    ConversationRepository,
    CustomerRepository,
    EscalationRepository,
    InventoryVehicleRepository,
    SalesLeadRepository,
    ServiceAppointmentRepository,
    ServiceHistoryRepository,
    ServiceSlotRepository,
    VehicleRepository,
)
from dealerai_ops.ml.schemas import NoShowPredictionRequest


class DealershipDomainService:
    """Read-oriented domain service for dealership operational lookups."""

    def __init__(self, session: Session) -> None:
        self.customers = CustomerRepository(session)
        self.vehicles = VehicleRepository(session)
        self.inventory = InventoryVehicleRepository(session)
        self.appointments = ServiceAppointmentRepository(session)
        self.history = ServiceHistoryRepository(session)
        self.slots = ServiceSlotRepository(session)
        self.leads = SalesLeadRepository(session)
        self.conversations = ConversationRepository(session)
        self.escalations = EscalationRepository(session)

    def identify_customer(self, customer_id: str) -> Customer | None:
        """Find a customer by synthetic customer ID."""
        return self.customers.get(customer_id)

    def retrieve_customer_vehicles(self, customer_id: str) -> list[Vehicle]:
        """Return vehicles owned by a customer."""
        return self.vehicles.list_for_customer(customer_id)

    def retrieve_customer_vehicle(self, customer_id: str, vehicle_id: str) -> Vehicle | None:
        """Return one vehicle only if it belongs to the customer."""
        return self.vehicles.get_for_customer(customer_id, vehicle_id)

    def retrieve_vehicle_details(self, vehicle_id: str) -> Vehicle | None:
        """Return an owned vehicle by ID."""
        return self.vehicles.get(vehicle_id)

    def retrieve_customer_appointments(
        self,
        customer_id: str,
        limit: int = 50,
    ) -> list[ServiceAppointment]:
        """Return recent service appointments for a customer."""
        return self.appointments.list_for_customer(customer_id, limit=limit)

    def retrieve_service_history(self, vehicle_id: str, limit: int = 50) -> list[ServiceHistory]:
        """Return completed service history for a vehicle."""
        return self.history.list_for_vehicle(vehicle_id, limit=limit)

    def search_inventory(
        self,
        make: str | None = None,
        model: str | None = None,
        limit: int = 25,
    ) -> list[InventoryVehicle]:
        """Search currently available inventory."""
        return self.inventory.search_available(make=make, model=model, limit=limit)

    def recommend_service_slots(
        self,
        bay_types: Sequence[str] | None = None,
        limit: int = 10,
    ) -> list[ServiceSlot]:
        """Return open service slots ordered by start time."""
        return self.slots.list_available(bay_types=bay_types, limit=limit)

    def build_no_show_request(self, appointment_id: str) -> NoShowPredictionRequest:
        """Build an ML inference request from a scheduled appointment."""
        appointment = self.appointments.get(appointment_id)
        if appointment is None:
            raise ValueError("Appointment not found.")
        customer = self.customers.get(appointment.customer_id)
        vehicle = self.vehicles.get(appointment.vehicle_id)
        if customer is None or vehicle is None:
            raise ValueError("Appointment has invalid customer or vehicle reference.")
        return NoShowPredictionRequest(
            appointment_type=appointment.appointment_type.value,
            channel=appointment.channel.value,
            lead_time_days=appointment.lead_time_days,
            estimated_duration_minutes=appointment.estimated_duration_minutes,
            is_first_service_visit=appointment.is_first_service_visit,
            prior_no_show_count_at_booking=appointment.prior_no_show_count_at_booking,
            prior_completed_appointments_at_booking=self.appointments.count_completed_before_customer(
                customer.id
            ),
            reminder_count=appointment.reminder_count,
            scheduled_day_of_week=appointment.scheduled_start_at.weekday(),
            scheduled_hour=appointment.scheduled_start_at.hour,
            days_since_customer_created_at_booking=max(
                0,
                (appointment.booked_at - customer.created_at).days,
            ),
            vehicle_age_years_at_booking=max(0, appointment.booked_at.year - vehicle.model_year),
            customer_distance_miles=float(customer.distance_miles),
            customer_loyalty_tier=customer.loyalty_tier,
            customer_acquisition_channel=customer.acquisition_channel,
            preferred_contact_method=customer.preferred_contact_method,
            marketing_opt_in=customer.marketing_opt_in,
        )

    def book_service_appointment(
        self,
        customer_id: str,
        vehicle_id: str,
        slot_id: str,
        appointment_type: AppointmentType,
        channel: AppointmentChannel,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> ServiceAppointment:
        """Book a confirmed appointment and reserve service-slot capacity."""
        customer = self.customers.get(customer_id)
        if customer is None:
            raise ValueError("Customer not found.")
        vehicle = self.vehicles.get_for_customer(customer_id, vehicle_id)
        if vehicle is None:
            raise ValueError("Vehicle not found for customer.")
        slot = self.slots.get(slot_id)
        if slot is None:
            raise ValueError("Service slot not found.")
        booked_at = _timestamp_like(slot.starts_at, now)
        if slot.starts_at <= booked_at:
            raise ValueError("Service slot must be in the future.")

        self.slots.reserve_capacity(slot)
        completed_count = self.appointments.count_completed_before_customer(customer_id)
        appointment = ServiceAppointment(
            id=_stable_id("apt", idempotency_key),
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            slot_id=slot_id,
            status=AppointmentStatus.CONFIRMED,
            appointment_type=appointment_type,
            channel=channel,
            scheduled_start_at=slot.starts_at,
            scheduled_end_at=slot.ends_at,
            booked_at=booked_at,
            confirmed_at=booked_at,
            canceled_at=None,
            completed_at=None,
            lead_time_days=max(0, (slot.starts_at - booked_at).days),
            estimated_duration_minutes=max(
                1,
                int((slot.ends_at - slot.starts_at).total_seconds() // 60),
            ),
            is_first_service_visit=completed_count == 0,
            prior_no_show_count_at_booking=self.appointments.count_no_show_before_customer(
                customer_id
            ),
            reminder_count=0,
            advisor_id=slot.advisor_id,
            created_at=booked_at,
        )
        return self.appointments.add(appointment)

    def reschedule_service_appointment(
        self,
        appointment_id: str,
        new_slot_id: str,
        now: datetime | None = None,
    ) -> ServiceAppointment:
        """Move an appointment to a new available slot."""
        appointment = self.appointments.get(appointment_id)
        if appointment is None:
            raise ValueError("Appointment not found.")
        if appointment.status in {AppointmentStatus.CANCELED, AppointmentStatus.COMPLETED}:
            raise ValueError("Appointment cannot be rescheduled from its current state.")
        new_slot = self.slots.get(new_slot_id)
        if new_slot is None:
            raise ValueError("New service slot not found.")
        rescheduled_at = _timestamp_like(new_slot.starts_at, now)
        if new_slot.starts_at <= rescheduled_at:
            raise ValueError("New service slot must be in the future.")

        if appointment.slot_id is not None and appointment.slot_id != new_slot_id:
            old_slot = self.slots.get(appointment.slot_id)
            if old_slot is not None:
                self.slots.release_capacity(old_slot)
        if appointment.slot_id != new_slot_id:
            self.slots.reserve_capacity(new_slot)

        appointment.slot_id = new_slot_id
        appointment.status = AppointmentStatus.RESCHEDULED
        appointment.scheduled_start_at = new_slot.starts_at
        appointment.scheduled_end_at = new_slot.ends_at
        appointment.lead_time_days = max(0, (new_slot.starts_at - rescheduled_at).days)
        appointment.estimated_duration_minutes = max(
            1,
            int((new_slot.ends_at - new_slot.starts_at).total_seconds() // 60),
        )
        self.appointments.session.flush()
        return appointment

    def cancel_service_appointment(
        self,
        appointment_id: str,
        now: datetime | None = None,
    ) -> ServiceAppointment:
        """Cancel an appointment and release associated slot capacity."""
        canceled_at = now or datetime.now(UTC)
        appointment = self.appointments.get(appointment_id)
        if appointment is None:
            raise ValueError("Appointment not found.")
        if appointment.status == AppointmentStatus.CANCELED:
            return appointment
        if appointment.status == AppointmentStatus.COMPLETED:
            raise ValueError("Completed appointments cannot be canceled.")
        if appointment.slot_id is not None:
            slot = self.slots.get(appointment.slot_id)
            if slot is not None:
                self.slots.release_capacity(slot)
        appointment.status = AppointmentStatus.CANCELED
        appointment.canceled_at = canceled_at
        self.appointments.session.flush()
        return appointment

    def create_sales_lead(
        self,
        source: str,
        desired_make: str,
        desired_model: str,
        budget_min: Decimal,
        budget_max: Decimal,
        idempotency_key: str,
        customer_id: str | None = None,
        inventory_vehicle_id: str | None = None,
        now: datetime | None = None,
    ) -> SalesLead:
        """Create a synthetic sales lead."""
        created_at = now or datetime.now(UTC)
        if customer_id is not None and self.customers.get(customer_id) is None:
            raise ValueError("Customer not found.")
        if inventory_vehicle_id is not None and self.inventory.get(inventory_vehicle_id) is None:
            raise ValueError("Inventory vehicle not found.")
        if budget_max < budget_min:
            raise ValueError("budget_max must be greater than or equal to budget_min.")
        lead = SalesLead(
            id=_stable_id("lead", idempotency_key),
            customer_id=customer_id,
            inventory_vehicle_id=inventory_vehicle_id,
            source=source,
            status=LeadStatus.NEW,
            desired_make=desired_make,
            desired_model=desired_model,
            budget_min=budget_min,
            budget_max=budget_max,
            created_at=created_at,
            contacted_at=None,
        )
        return self.leads.add(lead)

    def handoff_to_human(
        self,
        reason_code: str,
        severity: str,
        assigned_team: str,
        idempotency_key: str,
        conversation_id: str | None = None,
        customer_id: str | None = None,
        now: datetime | None = None,
    ) -> Escalation:
        """Create a human escalation record."""
        created_at = now or datetime.now(UTC)
        if customer_id is not None and self.customers.get(customer_id) is None:
            raise ValueError("Customer not found.")
        conversation = self.conversations.get(conversation_id) if conversation_id else None
        if conversation_id is not None and conversation is None:
            raise ValueError("Conversation not found.")
        if conversation is None:
            conversation = Conversation(
                id=_stable_id("conv", idempotency_key),
                customer_id=customer_id,
                sales_lead_id=None,
                channel="tool",
                status=ConversationStatus.ESCALATED,
                intent="human_handoff",
                started_at=created_at,
                ended_at=None,
                metadata_={"created_by": "handoff_to_human"},
                created_at=created_at,
            )
            self.conversations.add(conversation)
        escalation = Escalation(
            id=_stable_id("esc", idempotency_key),
            conversation_id=conversation.id,
            customer_id=customer_id or conversation.customer_id,
            reason_code=reason_code,
            severity=severity,
            status=EscalationStatus.OPEN,
            assigned_team=assigned_team,
            created_at=created_at,
            resolved_at=None,
        )
        return self.escalations.add(escalation)


def _stable_id(prefix: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _timestamp_like(reference: datetime, value: datetime | None = None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if reference.tzinfo is None and timestamp.tzinfo is not None:
        return timestamp.replace(tzinfo=None)
    if reference.tzinfo is not None and timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp
