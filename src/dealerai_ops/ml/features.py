"""Leakage-safe feature extraction for no-show prediction."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from dealerai_ops.db.models import Customer, ServiceAppointment, Vehicle
from dealerai_ops.domain.enums import AppointmentStatus
from dealerai_ops.domain.synthetic import SyntheticDataset
from dealerai_ops.ml.schemas import NoShowPredictionRequest

TARGET_COLUMN = "target_no_show"

NUMERIC_FEATURES: tuple[str, ...] = (
    "lead_time_days",
    "estimated_duration_minutes",
    "prior_no_show_count_at_booking",
    "prior_completed_appointments_at_booking",
    "reminder_count",
    "scheduled_day_of_week",
    "scheduled_hour",
    "days_since_customer_created_at_booking",
    "vehicle_age_years_at_booking",
    "customer_distance_miles",
)

CATEGORICAL_FEATURES: tuple[str, ...] = (
    "appointment_type",
    "channel",
    "is_first_service_visit",
    "customer_loyalty_tier",
    "customer_acquisition_channel",
    "preferred_contact_method",
    "marketing_opt_in",
)

FEATURE_COLUMNS: tuple[str, ...] = (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)

TARGET_LEAKAGE_COLUMNS: frozenset[str] = frozenset(
    {
        "status",
        "target_no_show",
        "completed_at",
        "canceled_at",
        "confirmed_at",
        "service_date",
        "service_codes",
        "total_amount",
        "technician_id",
        "appointment_id",
        "customer_id",
        "vehicle_id",
        "email_hash",
        "phone_last4",
        "synthetic_name",
        "current_mileage",
        "total_completed_appointments",
        "prior_no_show_count",
        "last_activity_at",
    },
)


@dataclass(frozen=True)
class FeatureSchema:
    """Serializable feature schema for model artifacts."""

    version: str
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    target_column: str
    leakage_blocklist: tuple[str, ...]

    @property
    def feature_columns(self) -> tuple[str, ...]:
        """Return all model input columns in deterministic order."""
        return (*self.numeric_features, *self.categorical_features)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable schema representation."""
        return {
            "version": self.version,
            "numeric_features": list(self.numeric_features),
            "categorical_features": list(self.categorical_features),
            "target_column": self.target_column,
            "leakage_blocklist": list(self.leakage_blocklist),
        }


NO_SHOW_FEATURE_SCHEMA = FeatureSchema(
    version="no-show-feature-schema-v1",
    numeric_features=NUMERIC_FEATURES,
    categorical_features=CATEGORICAL_FEATURES,
    target_column=TARGET_COLUMN,
    leakage_blocklist=tuple(sorted(TARGET_LEAKAGE_COLUMNS)),
)


def inspect_features_for_target_leakage(feature_columns: tuple[str, ...]) -> list[str]:
    """Return selected features that are known leakage risks."""
    selected = set(feature_columns)
    return sorted(selected.intersection(TARGET_LEAKAGE_COLUMNS))


def validate_no_target_leakage(feature_columns: tuple[str, ...]) -> None:
    """Raise when a selected feature is known to leak the target or future state."""
    leaking = inspect_features_for_target_leakage(feature_columns)
    if leaking:
        raise ValueError(f"Target leakage features are not allowed: {leaking}")


def build_training_frame(dataset: SyntheticDataset) -> tuple[pd.DataFrame, pd.Series]:
    """Build a leakage-safe training frame from synthetic appointments."""
    validate_no_target_leakage(NO_SHOW_FEATURE_SCHEMA.feature_columns)
    customers = {customer.id: customer for customer in dataset.customers}
    vehicles = {vehicle.id: vehicle for vehicle in dataset.vehicles}
    prior_no_shows: dict[str, int] = {}
    prior_completed: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    targets: list[int] = []

    appointments = sorted(dataset.service_appointments, key=lambda item: item.booked_at)
    for appointment in appointments:
        customer = customers[appointment.customer_id]
        vehicle = vehicles[appointment.vehicle_id]
        customer_no_shows = prior_no_shows.get(customer.id, 0)
        customer_completed = prior_completed.get(customer.id, 0)

        if appointment.status in {AppointmentStatus.NO_SHOW, AppointmentStatus.COMPLETED}:
            rows.append(
                feature_row_from_domain(
                    appointment=appointment,
                    customer=customer,
                    vehicle=vehicle,
                    prior_no_show_count_at_booking=customer_no_shows,
                    prior_completed_appointments_at_booking=customer_completed,
                ),
            )
            targets.append(1 if appointment.status == AppointmentStatus.NO_SHOW else 0)

        if appointment.status == AppointmentStatus.NO_SHOW:
            prior_no_shows[customer.id] = customer_no_shows + 1
        elif appointment.status == AppointmentStatus.COMPLETED:
            prior_completed[customer.id] = customer_completed + 1

    features = pd.DataFrame(rows, columns=NO_SHOW_FEATURE_SCHEMA.feature_columns)
    target = pd.Series(targets, name=TARGET_COLUMN)
    return features, target


def feature_row_from_domain(
    appointment: ServiceAppointment,
    customer: Customer,
    vehicle: Vehicle,
    prior_no_show_count_at_booking: int,
    prior_completed_appointments_at_booking: int,
) -> dict[str, object]:
    """Build a feature row using only booking-time information."""
    return {
        "lead_time_days": appointment.lead_time_days,
        "estimated_duration_minutes": appointment.estimated_duration_minutes,
        "prior_no_show_count_at_booking": prior_no_show_count_at_booking,
        "prior_completed_appointments_at_booking": prior_completed_appointments_at_booking,
        "reminder_count": appointment.reminder_count,
        "scheduled_day_of_week": appointment.scheduled_start_at.weekday(),
        "scheduled_hour": appointment.scheduled_start_at.hour,
        "days_since_customer_created_at_booking": max(
            0,
            (appointment.booked_at - customer.created_at).days,
        ),
        "vehicle_age_years_at_booking": max(
            0,
            appointment.booked_at.year - vehicle.model_year,
        ),
        "customer_distance_miles": float(customer.distance_miles),
        "appointment_type": appointment.appointment_type.value,
        "channel": appointment.channel.value,
        "is_first_service_visit": appointment.is_first_service_visit,
        "customer_loyalty_tier": customer.loyalty_tier,
        "customer_acquisition_channel": customer.acquisition_channel,
        "preferred_contact_method": customer.preferred_contact_method,
        "marketing_opt_in": customer.marketing_opt_in,
    }


def frame_from_prediction_request(request: NoShowPredictionRequest) -> pd.DataFrame:
    """Convert an inference request into the training-time feature order."""
    payload = request.model_dump()
    return pd.DataFrame([{column: payload[column] for column in FEATURE_COLUMNS}])


def dataset_fingerprint(features: pd.DataFrame, target: pd.Series, generated_at: datetime) -> str:
    """Return a stable fingerprint for the training data and schema."""
    payload: dict[str, Any] = {
        "rows": len(features),
        "target_sum": int(target.sum()),
        "feature_schema": NO_SHOW_FEATURE_SCHEMA.to_dict(),
        "generated_at": generated_at.isoformat(),
        "feature_sample": features.head(20).to_dict(orient="records"),
        "target_sample": target.head(20).tolist(),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
