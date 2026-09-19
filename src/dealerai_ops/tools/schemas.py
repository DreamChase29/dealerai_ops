"""Strict Pydantic input and output schemas for dealership tools."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from dealerai_ops.domain.enums import AppointmentChannel, AppointmentStatus, AppointmentType
from dealerai_ops.ml.schemas import RiskTier


class StrictSchema(BaseModel):
    """Base schema that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class CustomerSummary(StrictSchema):
    id: str
    synthetic_name: str
    preferred_contact_method: str
    acquisition_channel: str
    loyalty_tier: str
    distance_miles: float
    marketing_opt_in: bool
    prior_no_show_count: int
    total_completed_appointments: int


class VehicleSummary(StrictSchema):
    id: str
    customer_id: str
    vin: str
    make: str
    model: str
    trim: str
    model_year: int
    current_mileage: int
    warranty_end_date: datetime


class InventoryVehicleSummary(StrictSchema):
    id: str
    stock_number: str
    vin: str
    make: str
    model: str
    trim: str
    model_year: int
    body_style: str
    drivetrain: str
    fuel_type: str
    mileage: int
    list_price: Decimal
    status: str


class ServiceHistorySummary(StrictSchema):
    id: str
    appointment_id: str
    customer_id: str
    vehicle_id: str
    service_date: datetime
    odometer: int
    service_codes: list[str]
    total_amount: Decimal


class ServiceSlotSummary(StrictSchema):
    id: str
    starts_at: datetime
    ends_at: datetime
    bay_type: str
    advisor_id: str
    capacity: int
    booked_count: int
    remaining_capacity: int


class ServiceAppointmentSummary(StrictSchema):
    id: str
    customer_id: str
    vehicle_id: str
    slot_id: str | None
    status: AppointmentStatus
    appointment_type: AppointmentType
    channel: AppointmentChannel
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    lead_time_days: int


class SalesLeadSummary(StrictSchema):
    id: str
    customer_id: str | None
    inventory_vehicle_id: str | None
    source: str
    status: str
    desired_make: str
    desired_model: str
    budget_min: Decimal
    budget_max: Decimal
    created_at: datetime


class EscalationSummary(StrictSchema):
    id: str
    conversation_id: str
    customer_id: str | None
    reason_code: str
    severity: str
    status: str
    assigned_team: str
    created_at: datetime


class ConfirmationMixin(StrictSchema):
    confirmed: bool = False
    idempotency_key: str = Field(min_length=8, max_length=80)


class LookupCustomerInput(StrictSchema):
    customer_id: str = Field(min_length=1, max_length=32)


class LookupCustomerOutput(StrictSchema):
    found: bool
    customer: CustomerSummary | None = None


class GetCustomerVehicleInput(StrictSchema):
    customer_id: str = Field(min_length=1, max_length=32)
    vehicle_id: str = Field(min_length=1, max_length=32)


class GetCustomerVehicleOutput(StrictSchema):
    found: bool
    vehicle: VehicleSummary | None = None


class GetServiceHistoryInput(StrictSchema):
    vehicle_id: str = Field(min_length=1, max_length=32)
    limit: int = Field(default=25, ge=1, le=100)


class GetServiceHistoryOutput(StrictSchema):
    records: list[ServiceHistorySummary]


class SearchInventoryInput(StrictSchema):
    make: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=25, ge=1, le=100)


class SearchInventoryOutput(StrictSchema):
    vehicles: list[InventoryVehicleSummary]


class GetVehicleDetailsInput(StrictSchema):
    vehicle_id: str = Field(min_length=1, max_length=32)


class GetVehicleDetailsOutput(StrictSchema):
    found: bool
    vehicle: VehicleSummary | None = None


class GetAvailableServiceSlotsInput(StrictSchema):
    bay_types: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=100)


class GetAvailableServiceSlotsOutput(StrictSchema):
    slots: list[ServiceSlotSummary]


class PredictNoShowRiskInput(StrictSchema):
    appointment_id: str = Field(min_length=1, max_length=32)


class PredictNoShowRiskOutput(StrictSchema):
    probability: float = Field(ge=0, le=1)
    risk_tier: RiskTier
    model_version: str


class BookServiceAppointmentInput(ConfirmationMixin):
    customer_id: str = Field(min_length=1, max_length=32)
    vehicle_id: str = Field(min_length=1, max_length=32)
    slot_id: str = Field(min_length=1, max_length=32)
    appointment_type: AppointmentType
    channel: AppointmentChannel


class BookServiceAppointmentOutput(StrictSchema):
    appointment: ServiceAppointmentSummary


class RescheduleServiceAppointmentInput(ConfirmationMixin):
    appointment_id: str = Field(min_length=1, max_length=32)
    new_slot_id: str = Field(min_length=1, max_length=32)


class RescheduleServiceAppointmentOutput(StrictSchema):
    appointment: ServiceAppointmentSummary


class CancelServiceAppointmentInput(ConfirmationMixin):
    appointment_id: str = Field(min_length=1, max_length=32)


class CancelServiceAppointmentOutput(StrictSchema):
    appointment: ServiceAppointmentSummary


class CreateSalesLeadInput(ConfirmationMixin):
    source: str = Field(min_length=1, max_length=32)
    desired_make: str = Field(min_length=1, max_length=40)
    desired_model: str = Field(min_length=1, max_length=40)
    budget_min: Decimal = Field(ge=0)
    budget_max: Decimal = Field(ge=0)
    customer_id: str | None = Field(default=None, max_length=32)
    inventory_vehicle_id: str | None = Field(default=None, max_length=32)


class CreateSalesLeadOutput(StrictSchema):
    lead: SalesLeadSummary


class HandoffToHumanInput(StrictSchema):
    reason_code: str = Field(min_length=1, max_length=64)
    severity: str = Field(pattern="^(low|medium|high)$")
    assigned_team: str = Field(min_length=1, max_length=48)
    idempotency_key: str = Field(min_length=8, max_length=80)
    conversation_id: str | None = Field(default=None, max_length=32)
    customer_id: str | None = Field(default=None, max_length=32)


class HandoffToHumanOutput(StrictSchema):
    escalation: EscalationSummary
