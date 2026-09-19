"""Pydantic schemas for no-show prediction."""

from enum import StrEnum

from pydantic import BaseModel, Field


class RiskTier(StrEnum):
    """Operational no-show risk tiers."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class NoShowPredictionRequest(BaseModel):
    """Feature payload for service appointment no-show inference."""

    appointment_type: str
    channel: str
    lead_time_days: int = Field(ge=0, le=365)
    estimated_duration_minutes: int = Field(gt=0, le=480)
    is_first_service_visit: bool
    prior_no_show_count_at_booking: int = Field(ge=0)
    prior_completed_appointments_at_booking: int = Field(ge=0)
    reminder_count: int = Field(ge=0, le=10)
    scheduled_day_of_week: int = Field(ge=0, le=6)
    scheduled_hour: int = Field(ge=0, le=23)
    days_since_customer_created_at_booking: int = Field(ge=0)
    vehicle_age_years_at_booking: int = Field(ge=0, le=40)
    customer_distance_miles: float = Field(ge=0, le=250)
    customer_loyalty_tier: str
    customer_acquisition_channel: str
    preferred_contact_method: str
    marketing_opt_in: bool


class NoShowPredictionResponse(BaseModel):
    """Structured no-show prediction response."""

    probability: float = Field(ge=0, le=1)
    risk_tier: RiskTier
    model_version: str
