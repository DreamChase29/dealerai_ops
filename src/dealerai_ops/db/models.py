"""SQLAlchemy ORM models for the synthetic dealership domain."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dealerai_ops.db.base import Base
from dealerai_ops.domain.enums import (
    AppointmentChannel,
    AppointmentStatus,
    AppointmentType,
    ConversationStatus,
    EscalationStatus,
    InventoryStatus,
    LeadStatus,
    ToolExecutionStatus,
)


def utc_now() -> datetime:
    """Return the current UTC timestamp for ORM defaults."""
    return datetime.now(UTC)


class Customer(Base):
    """Synthetic dealership customer with behavior features for later ML."""

    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("distance_miles >= 0", name="ck_customers_distance_non_negative"),
        CheckConstraint("credit_band BETWEEN 1 AND 5", name="ck_customers_credit_band_range"),
        CheckConstraint("prior_no_show_count >= 0", name="ck_customers_prior_no_show_non_negative"),
        CheckConstraint(
            "total_completed_appointments >= 0",
            name="ck_customers_completed_appointments_non_negative",
        ),
        Index("ix_customers_loyalty_tier", "loyalty_tier"),
        Index("ix_customers_acquisition_channel", "acquisition_channel"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    synthetic_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    phone_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    preferred_contact_method: Mapped[str] = mapped_column(String(16), nullable=False)
    acquisition_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    loyalty_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    distance_miles: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    credit_band: Mapped[int] = mapped_column(Integer, nullable=False)
    marketing_opt_in: Mapped[bool] = mapped_column(nullable=False)
    prior_no_show_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_completed_appointments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="customer")
    appointments: Mapped[list["ServiceAppointment"]] = relationship(back_populates="customer")
    service_history: Mapped[list["ServiceHistory"]] = relationship(back_populates="customer")
    sales_leads: Mapped[list["SalesLead"]] = relationship(back_populates="customer")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="customer")


class Vehicle(Base):
    """Synthetic vehicle owned by a customer."""

    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("model_year BETWEEN 2000 AND 2027", name="ck_vehicles_model_year_range"),
        CheckConstraint("current_mileage >= 0", name="ck_vehicles_mileage_non_negative"),
        Index("ix_vehicles_customer_id", "customer_id"),
        Index("ix_vehicles_make_model", "make", "model"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    vin: Mapped[str] = mapped_column(String(17), nullable=False, unique=True)
    make: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    trim: Mapped[str] = mapped_column(String(40), nullable=False)
    model_year: Mapped[int] = mapped_column(Integer, nullable=False)
    current_mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    warranty_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="vehicles")
    appointments: Mapped[list["ServiceAppointment"]] = relationship(back_populates="vehicle")
    service_history: Mapped[list["ServiceHistory"]] = relationship(back_populates="vehicle")


class InventoryVehicle(Base):
    """Synthetic vehicle held in dealership inventory."""

    __tablename__ = "inventory_vehicles"
    __table_args__ = (
        CheckConstraint("model_year BETWEEN 2021 AND 2027", name="ck_inventory_model_year_range"),
        CheckConstraint("mileage >= 0", name="ck_inventory_mileage_non_negative"),
        CheckConstraint("msrp > 0", name="ck_inventory_msrp_positive"),
        CheckConstraint("list_price > 0", name="ck_inventory_list_price_positive"),
        Index("ix_inventory_make_model", "make", "model"),
        Index("ix_inventory_status", "status"),
        Index("ix_inventory_body_style", "body_style"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    stock_number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    vin: Mapped[str] = mapped_column(String(17), nullable=False, unique=True)
    make: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    trim: Mapped[str] = mapped_column(String(40), nullable=False)
    model_year: Mapped[int] = mapped_column(Integer, nullable=False)
    body_style: Mapped[str] = mapped_column(String(32), nullable=False)
    drivetrain: Mapped[str] = mapped_column(String(16), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(16), nullable=False)
    mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    exterior_color: Mapped[str] = mapped_column(String(24), nullable=False)
    interior_color: Mapped[str] = mapped_column(String(24), nullable=False)
    msrp: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    list_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[InventoryStatus] = mapped_column(
        SqlEnum(InventoryStatus, native_enum=False, length=24),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sales_leads: Mapped[list["SalesLead"]] = relationship(back_populates="inventory_vehicle")


class ServiceSlot(Base):
    """Future service capacity slot."""

    __tablename__ = "service_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_service_slots_end_after_start"),
        CheckConstraint("capacity > 0", name="ck_service_slots_capacity_positive"),
        CheckConstraint("booked_count >= 0", name="ck_service_slots_booked_non_negative"),
        CheckConstraint("booked_count <= capacity", name="ck_service_slots_booked_lte_capacity"),
        UniqueConstraint(
            "starts_at", "bay_type", "advisor_id", name="uq_service_slots_slot_bay_advisor"
        ),
        Index("ix_service_slots_starts_at", "starts_at"),
        Index("ix_service_slots_bay_type", "bay_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bay_type: Mapped[str] = mapped_column(String(32), nullable=False)
    advisor_id: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    booked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    appointments: Mapped[list["ServiceAppointment"]] = relationship(back_populates="slot")


class ServiceAppointment(Base):
    """Service appointment, including historical outcomes and future scheduled work."""

    __tablename__ = "service_appointments"
    __table_args__ = (
        CheckConstraint(
            "scheduled_end_at > scheduled_start_at", name="ck_appointments_end_after_start"
        ),
        CheckConstraint(
            "booked_at <= scheduled_start_at", name="ck_appointments_booked_before_start"
        ),
        CheckConstraint("estimated_duration_minutes > 0", name="ck_appointments_duration_positive"),
        CheckConstraint("lead_time_days >= 0", name="ck_appointments_lead_time_non_negative"),
        CheckConstraint("reminder_count >= 0", name="ck_appointments_reminders_non_negative"),
        CheckConstraint(
            "prior_no_show_count_at_booking >= 0", name="ck_appointments_prior_no_show_non_negative"
        ),
        Index("ix_appointments_customer_id", "customer_id"),
        Index("ix_appointments_vehicle_id", "vehicle_id"),
        Index("ix_appointments_slot_id", "slot_id"),
        Index("ix_appointments_status", "status"),
        Index("ix_appointments_scheduled_start", "scheduled_start_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    slot_id: Mapped[str | None] = mapped_column(ForeignKey("service_slots.id"), nullable=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        SqlEnum(AppointmentStatus, native_enum=False, length=24),
        nullable=False,
    )
    appointment_type: Mapped[AppointmentType] = mapped_column(
        SqlEnum(AppointmentType, native_enum=False, length=24),
        nullable=False,
    )
    channel: Mapped[AppointmentChannel] = mapped_column(
        SqlEnum(AppointmentChannel, native_enum=False, length=24),
        nullable=False,
    )
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_first_service_visit: Mapped[bool] = mapped_column(nullable=False)
    prior_no_show_count_at_booking: Mapped[int] = mapped_column(Integer, nullable=False)
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False)
    advisor_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="appointments")
    vehicle: Mapped[Vehicle] = relationship(back_populates="appointments")
    slot: Mapped[ServiceSlot | None] = relationship(back_populates="appointments")
    service_history: Mapped["ServiceHistory | None"] = relationship(
        back_populates="appointment",
        uselist=False,
    )
    tool_executions: Mapped[list["ToolExecution"]] = relationship(back_populates="appointment")


class ServiceHistory(Base):
    """Completed service work tied to a historical appointment."""

    __tablename__ = "service_history"
    __table_args__ = (
        CheckConstraint("odometer >= 0", name="ck_service_history_odometer_non_negative"),
        CheckConstraint("total_amount >= 0", name="ck_service_history_total_non_negative"),
        UniqueConstraint("appointment_id", name="uq_service_history_appointment"),
        Index("ix_service_history_customer_id", "customer_id"),
        Index("ix_service_history_vehicle_id", "vehicle_id"),
        Index("ix_service_history_service_date", "service_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("service_appointments.id"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    service_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    service_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    advisor_id: Mapped[str] = mapped_column(String(32), nullable=False)
    technician_id: Mapped[str] = mapped_column(String(32), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    appointment: Mapped[ServiceAppointment] = relationship(back_populates="service_history")
    customer: Mapped[Customer] = relationship(back_populates="service_history")
    vehicle: Mapped[Vehicle] = relationship(back_populates="service_history")


class SalesLead(Base):
    """Synthetic sales lead for inventory or desired vehicles."""

    __tablename__ = "sales_leads"
    __table_args__ = (
        CheckConstraint("budget_min >= 0", name="ck_sales_leads_budget_min_non_negative"),
        CheckConstraint("budget_max >= budget_min", name="ck_sales_leads_budget_range"),
        Index("ix_sales_leads_customer_id", "customer_id"),
        Index("ix_sales_leads_inventory_vehicle_id", "inventory_vehicle_id"),
        Index("ix_sales_leads_status", "status"),
        Index("ix_sales_leads_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    inventory_vehicle_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_vehicles.id"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[LeadStatus] = mapped_column(
        SqlEnum(LeadStatus, native_enum=False, length=24),
        nullable=False,
    )
    desired_make: Mapped[str] = mapped_column(String(40), nullable=False)
    desired_model: Mapped[str] = mapped_column(String(40), nullable=False)
    budget_min: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    budget_max: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer | None] = relationship(back_populates="sales_leads")
    inventory_vehicle: Mapped[InventoryVehicle | None] = relationship(back_populates="sales_leads")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="sales_lead")


class Conversation(Base):
    """Conversation transcript metadata without storing real PII."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_customer_id", "customer_id"),
        Index("ix_conversations_sales_lead_id", "sales_lead_id"),
        Index("ix_conversations_status", "status"),
        Index("ix_conversations_started_at", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    sales_lead_id: Mapped[str | None] = mapped_column(ForeignKey("sales_leads.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        SqlEnum(ConversationStatus, native_enum=False, length=32),
        nullable=False,
    )
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, str]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped[Customer | None] = relationship(back_populates="conversations")
    sales_lead: Mapped[SalesLead | None] = relationship(back_populates="conversations")
    tool_executions: Mapped[list["ToolExecution"]] = relationship(back_populates="conversation")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="conversation")


class ToolExecution(Base):
    """Audit trail for typed tool calls; no LLM direct writes are represented here."""

    __tablename__ = "tool_executions"
    __table_args__ = (
        Index("ix_tool_executions_conversation_id", "conversation_id"),
        Index("ix_tool_executions_request_id", "request_id"),
        Index("ix_tool_executions_status", "status"),
        Index("ix_tool_executions_tool_name", "tool_name"),
        Index("ix_tool_executions_idempotency_key", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    appointment_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_appointments.id"),
        nullable=True,
    )
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ToolExecutionStatus] = mapped_column(
        SqlEnum(ToolExecutionStatus, native_enum=False, length=32),
        nullable=False,
    )
    request_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(nullable=False, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    conversation: Mapped[Conversation | None] = relationship(back_populates="tool_executions")
    appointment: Mapped[ServiceAppointment | None] = relationship(back_populates="tool_executions")


class ToolIdempotencyRecord(Base):
    """Stable response record for idempotent write tools."""

    __tablename__ = "tool_idempotency_records"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tool_idempotency_key"),
        Index("ix_tool_idempotency_tool_name", "tool_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Escalation(Base):
    """Human escalation record for safety, policy, or operational handoff."""

    __tablename__ = "escalations"
    __table_args__ = (
        Index("ix_escalations_customer_id", "customer_id"),
        Index("ix_escalations_conversation_id", "conversation_id"),
        Index("ix_escalations_status", "status"),
        Index("ix_escalations_reason_code", "reason_code"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[EscalationStatus] = mapped_column(
        SqlEnum(EscalationStatus, native_enum=False, length=24),
        nullable=False,
    )
    assigned_team: Mapped[str] = mapped_column(String(48), nullable=False)
    package_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation] = relationship(back_populates="escalations")
    customer: Mapped[Customer | None] = relationship(back_populates="escalations")
