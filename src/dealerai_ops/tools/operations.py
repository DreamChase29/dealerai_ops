"""Deterministic dealership tool operations."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, cast

from pydantic import BaseModel

from dealerai_ops.db.models import (
    Customer,
    Escalation,
    InventoryVehicle,
    SalesLead,
    ServiceAppointment,
    ServiceHistory,
    ServiceSlot,
    Vehicle,
)
from dealerai_ops.domain.services import DealershipDomainService
from dealerai_ops.ml.schemas import NoShowPredictionRequest, NoShowPredictionResponse
from dealerai_ops.tools.schemas import (
    BookServiceAppointmentInput,
    BookServiceAppointmentOutput,
    CancelServiceAppointmentInput,
    CancelServiceAppointmentOutput,
    CreateSalesLeadInput,
    CreateSalesLeadOutput,
    CustomerSummary,
    EscalationSummary,
    GetAvailableServiceSlotsInput,
    GetAvailableServiceSlotsOutput,
    GetCustomerVehicleInput,
    GetCustomerVehicleOutput,
    GetServiceHistoryInput,
    GetServiceHistoryOutput,
    GetVehicleDetailsInput,
    GetVehicleDetailsOutput,
    HandoffToHumanInput,
    HandoffToHumanOutput,
    InventoryVehicleSummary,
    LookupCustomerInput,
    LookupCustomerOutput,
    PredictNoShowRiskInput,
    PredictNoShowRiskOutput,
    RescheduleServiceAppointmentInput,
    RescheduleServiceAppointmentOutput,
    SalesLeadSummary,
    SearchInventoryInput,
    SearchInventoryOutput,
    ServiceAppointmentSummary,
    ServiceHistorySummary,
    ServiceSlotSummary,
    VehicleSummary,
)
from dealerai_ops.tools.types import ToolMetadata, ToolRiskLevel


class NoShowPredictionProvider(Protocol):
    """Minimal prediction-service interface used by the tool layer."""

    def predict(self, request: NoShowPredictionRequest) -> NoShowPredictionResponse:
        """Return a no-show prediction."""


@dataclass(frozen=True)
class ToolRuntime:
    """Services available to deterministic tool implementations."""

    domain: DealershipDomainService
    no_show_service: NoShowPredictionProvider | None = None


ToolHandler = Callable[[ToolRuntime, BaseModel], BaseModel]


@dataclass(frozen=True)
class ToolDefinition:
    """Executable tool definition with metadata and schemas."""

    name: str
    description: str
    risk_level: ToolRiskLevel
    requires_confirmation: bool
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ToolHandler

    @property
    def metadata(self) -> ToolMetadata:
        """Return serializable metadata for the tool."""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            risk_level=self.risk_level,
            requires_confirmation=self.requires_confirmation,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
        )


def build_tool_registry() -> dict[str, ToolDefinition]:
    """Return all deterministic Phase 4 tool definitions."""
    tools = [
        ToolDefinition(
            name="lookup_customer",
            description="Look up a synthetic customer by customer ID.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=LookupCustomerInput,
            output_model=LookupCustomerOutput,
            handler=_lookup_customer,
        ),
        ToolDefinition(
            name="get_customer_vehicle",
            description="Return a vehicle owned by a specific synthetic customer.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=GetCustomerVehicleInput,
            output_model=GetCustomerVehicleOutput,
            handler=_get_customer_vehicle,
        ),
        ToolDefinition(
            name="get_service_history",
            description="Return completed service history records for an owned vehicle.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=GetServiceHistoryInput,
            output_model=GetServiceHistoryOutput,
            handler=_get_service_history,
        ),
        ToolDefinition(
            name="search_inventory",
            description="Search available synthetic dealership inventory.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=SearchInventoryInput,
            output_model=SearchInventoryOutput,
            handler=_search_inventory,
        ),
        ToolDefinition(
            name="get_vehicle_details",
            description="Return details for an owned synthetic vehicle.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=GetVehicleDetailsInput,
            output_model=GetVehicleDetailsOutput,
            handler=_get_vehicle_details,
        ),
        ToolDefinition(
            name="get_available_service_slots",
            description="Return available future service slots with remaining capacity.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=GetAvailableServiceSlotsInput,
            output_model=GetAvailableServiceSlotsOutput,
            handler=_get_available_service_slots,
        ),
        ToolDefinition(
            name="predict_no_show_risk",
            description="Predict no-show risk for a scheduled service appointment.",
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_confirmation=False,
            input_model=PredictNoShowRiskInput,
            output_model=PredictNoShowRiskOutput,
            handler=_predict_no_show_risk,
        ),
        ToolDefinition(
            name="book_service_appointment",
            description="Book a service appointment after explicit confirmation.",
            risk_level=ToolRiskLevel.HIGH_RISK_WRITE,
            requires_confirmation=True,
            input_model=BookServiceAppointmentInput,
            output_model=BookServiceAppointmentOutput,
            handler=_book_service_appointment,
        ),
        ToolDefinition(
            name="reschedule_service_appointment",
            description="Reschedule a service appointment after explicit confirmation.",
            risk_level=ToolRiskLevel.HIGH_RISK_WRITE,
            requires_confirmation=True,
            input_model=RescheduleServiceAppointmentInput,
            output_model=RescheduleServiceAppointmentOutput,
            handler=_reschedule_service_appointment,
        ),
        ToolDefinition(
            name="cancel_service_appointment",
            description="Cancel a service appointment after explicit confirmation.",
            risk_level=ToolRiskLevel.HIGH_RISK_WRITE,
            requires_confirmation=True,
            input_model=CancelServiceAppointmentInput,
            output_model=CancelServiceAppointmentOutput,
            handler=_cancel_service_appointment,
        ),
        ToolDefinition(
            name="create_sales_lead",
            description="Create a synthetic sales lead after explicit confirmation.",
            risk_level=ToolRiskLevel.LOW_RISK_WRITE,
            requires_confirmation=True,
            input_model=CreateSalesLeadInput,
            output_model=CreateSalesLeadOutput,
            handler=_create_sales_lead,
        ),
        ToolDefinition(
            name="handoff_to_human",
            description="Escalate a conversation or customer issue to a human team.",
            risk_level=ToolRiskLevel.ESCALATION,
            requires_confirmation=False,
            input_model=HandoffToHumanInput,
            output_model=HandoffToHumanOutput,
            handler=_handoff_to_human,
        ),
    ]
    return {tool.name: tool for tool in tools}


def _lookup_customer(runtime: ToolRuntime, payload: BaseModel) -> LookupCustomerOutput:
    request = cast(LookupCustomerInput, payload)
    customer = runtime.domain.identify_customer(request.customer_id)
    return LookupCustomerOutput(
        found=customer is not None,
        customer=_customer_summary(customer) if customer else None,
    )


def _get_customer_vehicle(runtime: ToolRuntime, payload: BaseModel) -> GetCustomerVehicleOutput:
    request = cast(GetCustomerVehicleInput, payload)
    vehicle = runtime.domain.retrieve_customer_vehicle(request.customer_id, request.vehicle_id)
    return GetCustomerVehicleOutput(
        found=vehicle is not None,
        vehicle=_vehicle_summary(vehicle) if vehicle else None,
    )


def _get_service_history(runtime: ToolRuntime, payload: BaseModel) -> GetServiceHistoryOutput:
    request = cast(GetServiceHistoryInput, payload)
    records = runtime.domain.retrieve_service_history(request.vehicle_id, limit=request.limit)
    return GetServiceHistoryOutput(records=[_service_history_summary(record) for record in records])


def _search_inventory(runtime: ToolRuntime, payload: BaseModel) -> SearchInventoryOutput:
    request = cast(SearchInventoryInput, payload)
    vehicles = runtime.domain.search_inventory(
        make=request.make,
        model=request.model,
        limit=request.limit,
    )
    return SearchInventoryOutput(vehicles=[_inventory_summary(vehicle) for vehicle in vehicles])


def _get_vehicle_details(runtime: ToolRuntime, payload: BaseModel) -> GetVehicleDetailsOutput:
    request = cast(GetVehicleDetailsInput, payload)
    vehicle = runtime.domain.retrieve_vehicle_details(request.vehicle_id)
    return GetVehicleDetailsOutput(
        found=vehicle is not None,
        vehicle=_vehicle_summary(vehicle) if vehicle else None,
    )


def _get_available_service_slots(
    runtime: ToolRuntime,
    payload: BaseModel,
) -> GetAvailableServiceSlotsOutput:
    request = cast(GetAvailableServiceSlotsInput, payload)
    slots = runtime.domain.recommend_service_slots(bay_types=request.bay_types, limit=request.limit)
    return GetAvailableServiceSlotsOutput(slots=[_slot_summary(slot) for slot in slots])


def _predict_no_show_risk(runtime: ToolRuntime, payload: BaseModel) -> PredictNoShowRiskOutput:
    if runtime.no_show_service is None:
        raise ValueError("No-show prediction service is unavailable.")
    request = cast(PredictNoShowRiskInput, payload)
    prediction_request = runtime.domain.build_no_show_request(request.appointment_id)
    prediction = runtime.no_show_service.predict(prediction_request)
    return PredictNoShowRiskOutput(
        probability=prediction.probability,
        risk_tier=prediction.risk_tier,
        model_version=prediction.model_version,
    )


def _book_service_appointment(
    runtime: ToolRuntime,
    payload: BaseModel,
) -> BookServiceAppointmentOutput:
    request = cast(BookServiceAppointmentInput, payload)
    appointment = runtime.domain.book_service_appointment(
        customer_id=request.customer_id,
        vehicle_id=request.vehicle_id,
        slot_id=request.slot_id,
        appointment_type=request.appointment_type,
        channel=request.channel,
        idempotency_key=request.idempotency_key,
    )
    return BookServiceAppointmentOutput(appointment=_appointment_summary(appointment))


def _reschedule_service_appointment(
    runtime: ToolRuntime,
    payload: BaseModel,
) -> RescheduleServiceAppointmentOutput:
    request = cast(RescheduleServiceAppointmentInput, payload)
    appointment = runtime.domain.reschedule_service_appointment(
        appointment_id=request.appointment_id,
        new_slot_id=request.new_slot_id,
    )
    return RescheduleServiceAppointmentOutput(appointment=_appointment_summary(appointment))


def _cancel_service_appointment(
    runtime: ToolRuntime,
    payload: BaseModel,
) -> CancelServiceAppointmentOutput:
    request = cast(CancelServiceAppointmentInput, payload)
    appointment = runtime.domain.cancel_service_appointment(request.appointment_id)
    return CancelServiceAppointmentOutput(appointment=_appointment_summary(appointment))


def _create_sales_lead(runtime: ToolRuntime, payload: BaseModel) -> CreateSalesLeadOutput:
    request = cast(CreateSalesLeadInput, payload)
    lead = runtime.domain.create_sales_lead(
        source=request.source,
        desired_make=request.desired_make,
        desired_model=request.desired_model,
        budget_min=request.budget_min,
        budget_max=request.budget_max,
        idempotency_key=request.idempotency_key,
        customer_id=request.customer_id,
        inventory_vehicle_id=request.inventory_vehicle_id,
    )
    return CreateSalesLeadOutput(lead=_sales_lead_summary(lead))


def _handoff_to_human(runtime: ToolRuntime, payload: BaseModel) -> HandoffToHumanOutput:
    request = cast(HandoffToHumanInput, payload)
    escalation = runtime.domain.handoff_to_human(
        reason_code=request.reason_code,
        severity=request.severity,
        assigned_team=request.assigned_team,
        idempotency_key=request.idempotency_key,
        conversation_id=request.conversation_id,
        customer_id=request.customer_id,
    )
    return HandoffToHumanOutput(escalation=_escalation_summary(escalation))


def _customer_summary(customer: Customer) -> CustomerSummary:
    return CustomerSummary(
        id=customer.id,
        synthetic_name=customer.synthetic_name,
        preferred_contact_method=customer.preferred_contact_method,
        acquisition_channel=customer.acquisition_channel,
        loyalty_tier=customer.loyalty_tier,
        distance_miles=float(customer.distance_miles),
        marketing_opt_in=customer.marketing_opt_in,
        prior_no_show_count=customer.prior_no_show_count,
        total_completed_appointments=customer.total_completed_appointments,
    )


def _vehicle_summary(vehicle: Vehicle) -> VehicleSummary:
    return VehicleSummary(
        id=vehicle.id,
        customer_id=vehicle.customer_id,
        vin=vehicle.vin,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        model_year=vehicle.model_year,
        current_mileage=vehicle.current_mileage,
        warranty_end_date=vehicle.warranty_end_date,
    )


def _inventory_summary(vehicle: InventoryVehicle) -> InventoryVehicleSummary:
    return InventoryVehicleSummary(
        id=vehicle.id,
        stock_number=vehicle.stock_number,
        vin=vehicle.vin,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        model_year=vehicle.model_year,
        body_style=vehicle.body_style,
        drivetrain=vehicle.drivetrain,
        fuel_type=vehicle.fuel_type,
        mileage=vehicle.mileage,
        list_price=vehicle.list_price,
        status=vehicle.status.value,
    )


def _service_history_summary(record: ServiceHistory) -> ServiceHistorySummary:
    return ServiceHistorySummary(
        id=record.id,
        appointment_id=record.appointment_id,
        customer_id=record.customer_id,
        vehicle_id=record.vehicle_id,
        service_date=record.service_date,
        odometer=record.odometer,
        service_codes=record.service_codes,
        total_amount=record.total_amount,
    )


def _slot_summary(slot: ServiceSlot) -> ServiceSlotSummary:
    return ServiceSlotSummary(
        id=slot.id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        bay_type=slot.bay_type,
        advisor_id=slot.advisor_id,
        capacity=slot.capacity,
        booked_count=slot.booked_count,
        remaining_capacity=slot.capacity - slot.booked_count,
    )


def _appointment_summary(appointment: ServiceAppointment) -> ServiceAppointmentSummary:
    return ServiceAppointmentSummary(
        id=appointment.id,
        customer_id=appointment.customer_id,
        vehicle_id=appointment.vehicle_id,
        slot_id=appointment.slot_id,
        status=appointment.status,
        appointment_type=appointment.appointment_type,
        channel=appointment.channel,
        scheduled_start_at=appointment.scheduled_start_at,
        scheduled_end_at=appointment.scheduled_end_at,
        lead_time_days=appointment.lead_time_days,
    )


def _sales_lead_summary(lead: SalesLead) -> SalesLeadSummary:
    return SalesLeadSummary(
        id=lead.id,
        customer_id=lead.customer_id,
        inventory_vehicle_id=lead.inventory_vehicle_id,
        source=lead.source,
        status=lead.status.value,
        desired_make=lead.desired_make,
        desired_model=lead.desired_model,
        budget_min=Decimal(lead.budget_min),
        budget_max=Decimal(lead.budget_max),
        created_at=lead.created_at,
    )


def _escalation_summary(escalation: Escalation) -> EscalationSummary:
    return EscalationSummary(
        id=escalation.id,
        conversation_id=escalation.conversation_id,
        customer_id=escalation.customer_id,
        reason_code=escalation.reason_code,
        severity=escalation.severity,
        status=escalation.status.value,
        assigned_team=escalation.assigned_team,
        created_at=escalation.created_at,
    )
