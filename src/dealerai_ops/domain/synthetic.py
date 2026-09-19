"""Deterministic synthetic dealership data generation."""

import hashlib
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

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
    ToolExecution,
    ToolIdempotencyRecord,
    Vehicle,
)
from dealerai_ops.domain.enums import (
    AppointmentChannel,
    AppointmentStatus,
    AppointmentType,
    ConversationStatus,
    EscalationReason,
    EscalationStatus,
    InventoryStatus,
    LeadStatus,
    ToolExecutionStatus,
)

DEFAULT_SYNTHETIC_SEED = 20260811
DEFAULT_AS_OF = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

MAKES_MODELS: dict[str, list[str]] = {
    "Toyota": ["Camry", "Corolla", "RAV4", "Tacoma", "Highlander"],
    "Honda": ["Accord", "Civic", "CR-V", "Pilot", "Ridgeline"],
    "Ford": ["F-150", "Escape", "Explorer", "Bronco Sport", "Maverick"],
    "Chevrolet": ["Silverado", "Equinox", "Traverse", "Malibu", "Colorado"],
    "Hyundai": ["Elantra", "Sonata", "Tucson", "Santa Fe", "Palisade"],
    "Kia": ["Forte", "K5", "Sportage", "Sorento", "Telluride"],
}

TRIMS = ["Base", "SE", "EX", "Touring", "Limited", "XLE", "Sport"]
BODY_STYLES = ["sedan", "suv", "truck", "crossover", "hatchback"]
DRIVETRAINS = ["fwd", "rwd", "awd", "4wd"]
FUEL_TYPES = ["gas", "hybrid", "plug_in_hybrid", "electric"]
COLORS = ["white", "black", "silver", "blue", "red", "gray", "green"]
ADVISORS = [f"adv_{idx:03d}" for idx in range(1, 13)]
TECHNICIANS = [f"tech_{idx:03d}" for idx in range(1, 25)]
BAY_TYPES = ["quick_service", "standard", "diagnostic", "heavy_repair"]
SERVICE_CODES = {
    AppointmentType.MAINTENANCE: ["OIL", "TIRE_ROTATION", "MULTIPOINT"],
    AppointmentType.REPAIR: ["BRAKES", "SUSPENSION", "ELECTRICAL"],
    AppointmentType.DIAGNOSTIC: ["DIAG", "CHECK_ENGINE", "SCAN"],
    AppointmentType.RECALL: ["RECALL", "INSPECTION"],
    AppointmentType.TIRE: ["TIRE_REPLACE", "ALIGNMENT"],
}


@dataclass(frozen=True)
class SyntheticDatasetCounts:
    """Target row counts for deterministic synthetic data generation."""

    customers: int = 2_000
    owned_vehicles: int = 2_500
    inventory_vehicles: int = 300
    historical_appointments: int = 5_000
    future_service_days: int = 60
    sales_leads: int = 600
    conversations: int = 800
    tool_executions: int = 1_100
    escalations: int = 80


@dataclass
class SyntheticDataset:
    """Generated synthetic ORM objects grouped by entity type."""

    customers: list[Customer]
    vehicles: list[Vehicle]
    inventory_vehicles: list[InventoryVehicle]
    service_slots: list[ServiceSlot]
    service_appointments: list[ServiceAppointment]
    service_history: list[ServiceHistory]
    sales_leads: list[SalesLead]
    conversations: list[Conversation]
    tool_executions: list[ToolExecution]
    idempotency_records: list[ToolIdempotencyRecord]
    escalations: list[Escalation]

    def all_records(self) -> list[object]:
        """Return records in dependency-safe insert order."""
        return [
            *self.customers,
            *self.vehicles,
            *self.inventory_vehicles,
            *self.service_slots,
            *self.service_appointments,
            *self.service_history,
            *self.sales_leads,
            *self.conversations,
            *self.tool_executions,
            *self.idempotency_records,
            *self.escalations,
        ]

    def summary(self) -> dict[str, int]:
        """Return entity counts for scripts and tests."""
        return {
            "customers": len(self.customers),
            "vehicles": len(self.vehicles),
            "inventory_vehicles": len(self.inventory_vehicles),
            "service_slots": len(self.service_slots),
            "service_appointments": len(self.service_appointments),
            "service_history": len(self.service_history),
            "sales_leads": len(self.sales_leads),
            "conversations": len(self.conversations),
            "tool_executions": len(self.tool_executions),
            "idempotency_records": len(self.idempotency_records),
            "escalations": len(self.escalations),
        }


class HasStableId(Protocol):
    """Structural protocol for generated ORM objects with stable IDs."""

    id: str


def generate_synthetic_dataset(
    counts: SyntheticDatasetCounts | None = None,
    seed: int = DEFAULT_SYNTHETIC_SEED,
    as_of: datetime = DEFAULT_AS_OF,
) -> SyntheticDataset:
    """Generate deterministic synthetic dealership data."""
    resolved_counts = counts or SyntheticDatasetCounts()
    rng = random.Random(seed)  # noqa: S311 - deterministic synthetic data, not security.
    customers = _generate_customers(resolved_counts.customers, rng, as_of)
    vehicles = _generate_owned_vehicles(resolved_counts.owned_vehicles, customers, rng, as_of)
    inventory = _generate_inventory_vehicles(resolved_counts.inventory_vehicles, rng, as_of)
    slots = _generate_future_service_slots(resolved_counts.future_service_days, rng, as_of)
    appointments, history = _generate_historical_appointments(
        resolved_counts.historical_appointments,
        customers,
        vehicles,
        rng,
        as_of,
    )
    leads = _generate_sales_leads(resolved_counts.sales_leads, customers, inventory, rng, as_of)
    conversations = _generate_conversations(
        resolved_counts.conversations, customers, leads, rng, as_of
    )
    tool_executions = _generate_tool_executions(
        resolved_counts.tool_executions,
        conversations,
        appointments,
        rng,
    )
    escalations = _generate_escalations(resolved_counts.escalations, conversations, rng)

    return SyntheticDataset(
        customers=customers,
        vehicles=vehicles,
        inventory_vehicles=inventory,
        service_slots=slots,
        service_appointments=appointments,
        service_history=history,
        sales_leads=leads,
        conversations=conversations,
        tool_executions=tool_executions,
        idempotency_records=[],
        escalations=escalations,
    )


def seed_session(session: Session, dataset: SyntheticDataset) -> dict[str, int]:
    """Insert a synthetic dataset into a database session and commit it."""
    session.add_all(dataset.all_records())
    session.commit()
    return dataset.summary()


def _generate_customers(count: int, rng: random.Random, as_of: datetime) -> list[Customer]:
    first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn"]
    last_names = ["Parker", "Hayes", "Brooks", "Reed", "Sullivan", "Foster", "Bennett", "Cole"]
    channels = ["organic_search", "service_referral", "walk_in", "marketplace", "email_campaign"]
    contact_methods = ["email", "sms", "phone"]
    loyalty_tiers = ["standard", "silver", "gold", "platinum"]
    customers: list[Customer] = []

    for idx in range(1, count + 1):
        created_at = as_of - timedelta(days=rng.randint(90, 2_400))
        customer_key = f"synthetic-customer-{idx:06d}"
        customers.append(
            Customer(
                id=_id("cus", idx),
                synthetic_name=f"{rng.choice(first_names)} {rng.choice(last_names)} {idx:04d}",
                email_hash=hashlib.sha256(customer_key.encode("utf-8")).hexdigest(),
                phone_last4=f"{rng.randint(0, 9999):04d}",
                preferred_contact_method=rng.choice(contact_methods),
                acquisition_channel=rng.choice(channels),
                loyalty_tier=rng.choices(loyalty_tiers, weights=[50, 25, 18, 7], k=1)[0],
                distance_miles=_money(rng.uniform(1, 48)),
                credit_band=rng.randint(1, 5),
                marketing_opt_in=rng.random() < 0.72,
                prior_no_show_count=0,
                total_completed_appointments=0,
                created_at=created_at,
                last_activity_at=created_at,
            ),
        )
    return customers


def _generate_owned_vehicles(
    count: int,
    customers: list[Customer],
    rng: random.Random,
    as_of: datetime,
) -> list[Vehicle]:
    vehicles: list[Vehicle] = []
    for idx in range(1, count + 1):
        customer = customers[idx - 1] if idx <= len(customers) else rng.choice(customers)
        make = rng.choice(list(MAKES_MODELS))
        model = rng.choice(MAKES_MODELS[make])
        model_year = rng.randint(2012, 2026)
        purchase_date = as_of - timedelta(days=rng.randint(30, 2_300))
        warranty_years = rng.choice([3, 3, 5, 7])
        vehicles.append(
            Vehicle(
                id=_id("veh", idx),
                customer_id=customer.id,
                vin=_vin("DAX", idx),
                make=make,
                model=model,
                trim=rng.choice(TRIMS),
                model_year=model_year,
                current_mileage=rng.randint(4_000, 165_000),
                purchase_date=purchase_date,
                warranty_end_date=purchase_date + timedelta(days=365 * warranty_years),
                created_at=purchase_date,
            ),
        )
    return vehicles


def _generate_inventory_vehicles(
    count: int,
    rng: random.Random,
    as_of: datetime,
) -> list[InventoryVehicle]:
    inventory: list[InventoryVehicle] = []
    for idx in range(1, count + 1):
        make = rng.choice(list(MAKES_MODELS))
        model = rng.choice(MAKES_MODELS[make])
        msrp = _money(rng.uniform(25_000, 74_000))
        discount = Decimal(str(rng.uniform(0, 4_500))).quantize(Decimal("0.01"))
        inventory.append(
            InventoryVehicle(
                id=_id("inv", idx),
                stock_number=f"STK{idx:06d}",
                vin=_vin("DXY", idx),
                make=make,
                model=model,
                trim=rng.choice(TRIMS),
                model_year=rng.randint(2023, 2027),
                body_style=rng.choice(BODY_STYLES),
                drivetrain=rng.choice(DRIVETRAINS),
                fuel_type=rng.choice(FUEL_TYPES),
                mileage=rng.choice([0, rng.randint(5, 8_500)]),
                exterior_color=rng.choice(COLORS),
                interior_color=rng.choice(["black", "gray", "tan"]),
                msrp=msrp,
                list_price=max(Decimal("15000.00"), msrp - discount),
                status=rng.choices(
                    list(InventoryStatus),
                    weights=[70, 10, 8, 12],
                    k=1,
                )[0],
                created_at=as_of - timedelta(days=rng.randint(1, 120)),
            ),
        )
    return inventory


def _generate_future_service_slots(
    future_days: int,
    rng: random.Random,
    as_of: datetime,
) -> list[ServiceSlot]:
    slots: list[ServiceSlot] = []
    slot_idx = 1
    start_hours = [8, 10, 12, 14, 16]

    for day_offset in range(1, future_days + 1):
        slot_date = as_of + timedelta(days=day_offset)
        if slot_date.weekday() == 6:
            continue
        for bay_type in BAY_TYPES:
            for hour in start_hours:
                starts_at = slot_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                duration_hours = 1 if bay_type == "quick_service" else 2
                capacity = 4 if bay_type == "quick_service" else rng.randint(1, 3)
                slots.append(
                    ServiceSlot(
                        id=_id("slot", slot_idx),
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(hours=duration_hours),
                        bay_type=bay_type,
                        advisor_id=ADVISORS[(slot_idx - 1) % len(ADVISORS)],
                        capacity=capacity,
                        booked_count=rng.randint(0, capacity - 1),
                        created_at=as_of,
                    ),
                )
                slot_idx += 1
    return slots


def _generate_historical_appointments(
    count: int,
    customers: list[Customer],
    vehicles: list[Vehicle],
    rng: random.Random,
    as_of: datetime,
) -> tuple[list[ServiceAppointment], list[ServiceHistory]]:
    vehicles_by_customer: dict[str, list[Vehicle]] = defaultdict(list)
    for vehicle in vehicles:
        vehicles_by_customer[vehicle.customer_id].append(vehicle)

    customers_by_id = {customer.id: customer for customer in customers}
    no_show_counts: dict[str, int] = defaultdict(int)
    completed_counts: dict[str, int] = defaultdict(int)
    latest_activity: dict[str, datetime] = {
        customer.id: customer.created_at for customer in customers
    }
    appointments: list[ServiceAppointment] = []
    history: list[ServiceHistory] = []

    for idx in range(1, count + 1):
        customer = rng.choice(customers)
        customer_vehicles = vehicles_by_customer[customer.id]
        vehicle = rng.choice(customer_vehicles)
        appointment_type = rng.choices(
            list(AppointmentType),
            weights=[52, 20, 12, 6, 10],
            k=1,
        )[0]
        channel = rng.choices(
            list(AppointmentChannel),
            weights=[38, 28, 16, 8, 10],
            k=1,
        )[0]
        lead_time_days = rng.randint(0, 45)
        scheduled_start = _historical_start(as_of, rng)
        duration = _duration_minutes(appointment_type, rng)
        booked_at = scheduled_start - timedelta(days=lead_time_days, hours=rng.randint(1, 8))
        reminder_count = rng.choices([0, 1, 2, 3], weights=[10, 25, 45, 20], k=1)[0]
        prior_no_shows = no_show_counts[customer.id]
        status = _appointment_status(
            customer, prior_no_shows, lead_time_days, reminder_count, channel, rng
        )
        completed_at = (
            scheduled_start + timedelta(minutes=duration)
            if status == AppointmentStatus.COMPLETED
            else None
        )
        canceled_at = (
            booked_at + (scheduled_start - booked_at) / 2
            if status in {AppointmentStatus.CANCELED, AppointmentStatus.RESCHEDULED}
            else None
        )
        confirmed_at = (
            scheduled_start - timedelta(days=rng.randint(1, max(1, min(5, lead_time_days))))
            if status in {AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED}
            and lead_time_days > 0
            else None
        )

        appointment = ServiceAppointment(
            id=_id("apt", idx),
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            slot_id=None,
            status=status,
            appointment_type=appointment_type,
            channel=channel,
            scheduled_start_at=scheduled_start,
            scheduled_end_at=scheduled_start + timedelta(minutes=duration),
            booked_at=booked_at,
            confirmed_at=confirmed_at,
            canceled_at=canceled_at,
            completed_at=completed_at,
            lead_time_days=lead_time_days,
            estimated_duration_minutes=duration,
            is_first_service_visit=completed_counts[customer.id] == 0,
            prior_no_show_count_at_booking=prior_no_shows,
            reminder_count=reminder_count,
            advisor_id=rng.choice(ADVISORS),
            created_at=booked_at,
        )
        appointments.append(appointment)
        latest_activity[customer.id] = max(latest_activity[customer.id], scheduled_start)

        if status == AppointmentStatus.NO_SHOW:
            no_show_counts[customer.id] += 1
        elif status == AppointmentStatus.COMPLETED:
            completed_counts[customer.id] += 1
            history.append(
                _service_history_from_appointment(len(history) + 1, appointment, vehicle, rng)
            )

    for customer_id, customer in customers_by_id.items():
        customer.prior_no_show_count = no_show_counts[customer_id]
        customer.total_completed_appointments = completed_counts[customer_id]
        customer.last_activity_at = latest_activity[customer_id]

    return appointments, history


def _generate_sales_leads(
    count: int,
    customers: list[Customer],
    inventory: list[InventoryVehicle],
    rng: random.Random,
    as_of: datetime,
) -> list[SalesLead]:
    leads: list[SalesLead] = []
    sources = ["website", "phone", "walk_in", "marketplace", "service_drive"]
    for idx in range(1, count + 1):
        customer = rng.choice(customers) if rng.random() < 0.86 else None
        inventory_vehicle = rng.choice(inventory) if rng.random() < 0.72 else None
        make = inventory_vehicle.make if inventory_vehicle else rng.choice(list(MAKES_MODELS))
        model = inventory_vehicle.model if inventory_vehicle else rng.choice(MAKES_MODELS[make])
        budget_min = Decimal(rng.randrange(20_000, 52_000, 500))
        budget_max = budget_min + Decimal(rng.randrange(5_000, 25_000, 500))
        created_at = as_of - timedelta(days=rng.randint(0, 180), hours=rng.randint(0, 23))
        status = rng.choices(list(LeadStatus), weights=[35, 28, 18, 7, 12], k=1)[0]
        leads.append(
            SalesLead(
                id=_id("lead", idx),
                customer_id=customer.id if customer else None,
                inventory_vehicle_id=inventory_vehicle.id if inventory_vehicle else None,
                source=rng.choice(sources),
                status=status,
                desired_make=make,
                desired_model=model,
                budget_min=budget_min,
                budget_max=budget_max,
                created_at=created_at,
                contacted_at=created_at + timedelta(hours=rng.randint(1, 72))
                if status != LeadStatus.NEW
                else None,
            ),
        )
    return leads


def _generate_conversations(
    count: int,
    customers: list[Customer],
    leads: list[SalesLead],
    rng: random.Random,
    as_of: datetime,
) -> list[Conversation]:
    conversations: list[Conversation] = []
    intents = ["service_booking", "inventory_search", "policy_question", "lead_followup", "billing"]
    for idx in range(1, count + 1):
        lead = rng.choice(leads) if leads and rng.random() < 0.34 else None
        customer_id = lead.customer_id if lead and lead.customer_id else rng.choice(customers).id
        started_at = as_of - timedelta(days=rng.randint(0, 90), minutes=rng.randint(0, 1_440))
        status = rng.choices(
            list(ConversationStatus),
            weights=[28, 20, 8, 44],
            k=1,
        )[0]
        conversations.append(
            Conversation(
                id=_id("conv", idx),
                customer_id=customer_id,
                sales_lead_id=lead.id if lead else None,
                channel=rng.choice(["web_chat", "sms", "phone", "email"]),
                status=status,
                intent=rng.choice(intents),
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=rng.randint(4, 45))
                if status == ConversationStatus.CLOSED
                else None,
                metadata_={"synthetic": "true"},
                created_at=started_at,
            ),
        )
    return conversations


def _generate_tool_executions(
    count: int,
    conversations: list[Conversation],
    appointments: list[ServiceAppointment],
    rng: random.Random,
) -> list[ToolExecution]:
    executions: list[ToolExecution] = []
    tool_names = [
        "lookup_customer",
        "lookup_vehicle",
        "search_inventory",
        "check_service_slots",
        "estimate_no_show_risk",
        "create_sales_lead",
    ]
    transactional_tools = {"create_sales_lead"}
    for idx in range(1, count + 1):
        conversation = rng.choice(conversations)
        tool_name = rng.choice(tool_names)
        requires_confirmation = tool_name in transactional_tools
        status = (
            ToolExecutionStatus.REQUIRES_CONFIRMATION
            if requires_confirmation
            else ToolExecutionStatus.SUCCEEDED
        )
        appointment = rng.choice(appointments) if tool_name == "estimate_no_show_risk" else None
        executions.append(
            ToolExecution(
                id=_id("tool", idx),
                conversation_id=conversation.id,
                appointment_id=appointment.id if appointment else None,
                request_id=f"request_{idx:08d}",
                tool_name=tool_name,
                status=status,
                request_payload={"synthetic_request_id": f"req_{idx:06d}"},
                response_payload={"ok": True, "synthetic": True},
                requires_confirmation=requires_confirmation,
                idempotency_key=f"idem_{idx:08d}",
                created_at=conversation.started_at + timedelta(seconds=rng.randint(1, 120)),
            ),
        )
    return executions


def _generate_escalations(
    count: int,
    conversations: list[Conversation],
    rng: random.Random,
) -> list[Escalation]:
    escalations: list[Escalation] = []
    reason_codes = list(EscalationReason)
    teams = ["service_manager", "sales_manager", "customer_care", "fixed_ops"]
    for idx in range(1, count + 1):
        conversation = rng.choice(conversations)
        status = rng.choices(list(EscalationStatus), weights=[35, 15, 45, 5], k=1)[0]
        created_at = conversation.started_at + timedelta(minutes=rng.randint(1, 30))
        escalations.append(
            Escalation(
                id=_id("esc", idx),
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                reason_code=rng.choice(reason_codes).value,
                severity=rng.choices(["low", "medium", "high"], weights=[45, 40, 15], k=1)[0],
                status=status,
                assigned_team=rng.choice(teams),
                created_at=created_at,
                resolved_at=created_at + timedelta(hours=rng.randint(1, 72))
                if status == EscalationStatus.RESOLVED
                else None,
            ),
        )
    return escalations


def _appointment_status(
    customer: Customer,
    prior_no_shows: int,
    lead_time_days: int,
    reminder_count: int,
    channel: AppointmentChannel,
    rng: random.Random,
) -> AppointmentStatus:
    no_show_probability = 0.055
    no_show_probability += min(prior_no_shows, 5) * 0.025
    no_show_probability += max(0, lead_time_days - 14) * 0.0025
    no_show_probability += 0.025 if reminder_count == 0 else -0.01 * min(reminder_count, 2)
    no_show_probability += (
        0.02 if channel in {AppointmentChannel.WEB, AppointmentChannel.SMS} else 0
    )
    no_show_probability += 0.018 if customer.distance_miles > Decimal("30.00") else 0
    no_show_probability = min(max(no_show_probability, 0.015), 0.32)

    sample = rng.random()
    if sample < no_show_probability:
        return AppointmentStatus.NO_SHOW
    if sample < no_show_probability + 0.075:
        return AppointmentStatus.CANCELED
    if sample < no_show_probability + 0.105:
        return AppointmentStatus.RESCHEDULED
    if sample < no_show_probability + 0.135:
        return AppointmentStatus.CONFIRMED
    return AppointmentStatus.COMPLETED


def _service_history_from_appointment(
    history_idx: int,
    appointment: ServiceAppointment,
    vehicle: Vehicle,
    rng: random.Random,
) -> ServiceHistory:
    base_amount = {
        AppointmentType.MAINTENANCE: 145,
        AppointmentType.REPAIR: 520,
        AppointmentType.DIAGNOSTIC: 180,
        AppointmentType.RECALL: 0,
        AppointmentType.TIRE: 680,
    }[appointment.appointment_type]
    service_codes = SERVICE_CODES[appointment.appointment_type]
    return ServiceHistory(
        id=_id("hist", history_idx),
        appointment_id=appointment.id,
        customer_id=appointment.customer_id,
        vehicle_id=appointment.vehicle_id,
        service_date=appointment.completed_at or appointment.scheduled_end_at,
        odometer=max(0, vehicle.current_mileage - rng.randint(0, 8_000)),
        service_codes=rng.sample(service_codes, k=min(len(service_codes), rng.randint(1, 2))),
        advisor_id=appointment.advisor_id,
        technician_id=rng.choice(TECHNICIANS),
        total_amount=_money(base_amount + rng.uniform(0, 350)),
        created_at=appointment.completed_at or appointment.scheduled_end_at,
    )


def _historical_start(as_of: datetime, rng: random.Random) -> datetime:
    days_back = rng.randint(1, 730)
    hour = rng.choice([8, 9, 10, 11, 13, 14, 15, 16])
    starts_at = as_of - timedelta(days=days_back)
    while starts_at.weekday() == 6:
        starts_at -= timedelta(days=1)
    return starts_at.replace(hour=hour, minute=rng.choice([0, 15, 30]), second=0, microsecond=0)


def _duration_minutes(appointment_type: AppointmentType, rng: random.Random) -> int:
    ranges = {
        AppointmentType.MAINTENANCE: (45, 90),
        AppointmentType.REPAIR: (90, 240),
        AppointmentType.DIAGNOSTIC: (60, 150),
        AppointmentType.RECALL: (45, 120),
        AppointmentType.TIRE: (60, 120),
    }
    low, high = ranges[appointment_type]
    return rng.randrange(low, high + 1, 15)


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _id(prefix: str, idx: int) -> str:
    return f"{prefix}_{idx:08d}"


def _vin(prefix: str, idx: int) -> str:
    return f"{prefix}{idx:014d}"


def ids_are_unique(records: Iterable[HasStableId]) -> bool:
    """Return whether all ORM objects with an ``id`` attribute have unique IDs."""
    ids = [record.id for record in records]
    return len(ids) == len(set(ids))
