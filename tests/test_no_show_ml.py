from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from dealerai_ops.core.config import Settings
from dealerai_ops.domain.synthetic import SyntheticDatasetCounts, generate_synthetic_dataset
from dealerai_ops.main import create_app
from dealerai_ops.ml.features import (
    FEATURE_COLUMNS,
    build_training_frame,
    inspect_features_for_target_leakage,
    validate_no_target_leakage,
)
from dealerai_ops.ml.risk import RiskTier, risk_tier_for_probability, threshold_analysis
from dealerai_ops.ml.schemas import NoShowPredictionRequest
from dealerai_ops.ml.service import NoShowPredictionService, get_cached_no_show_prediction_service
from dealerai_ops.ml.training import (
    FEATURE_SCHEMA_FILENAME,
    METADATA_FILENAME,
    METRICS_FILENAME,
    MODEL_FILENAME,
    load_model_artifact,
    train_and_serialize_model,
)


@pytest.fixture(scope="module")
def small_training_frame() -> tuple[pd.DataFrame, pd.Series]:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=180,
            owned_vehicles=220,
            inventory_vehicles=30,
            historical_appointments=900,
            future_service_days=7,
            sales_leads=40,
            conversations=50,
            tool_executions=70,
            escalations=8,
        ),
        seed=321,
    )
    return build_training_frame(dataset)


@pytest.fixture(scope="module")
def trained_model_dir(
    tmp_path_factory: pytest.TempPathFactory,
    small_training_frame: tuple[pd.DataFrame, pd.Series],
) -> Path:
    model_dir = tmp_path_factory.mktemp("no_show_model")
    features, target = small_training_frame
    train_and_serialize_model(
        features=features,
        target=target,
        model_dir=model_dir,
        model_version="test-no-show-v1",
        dataset_version="synthetic-test",
        dataset_generated_at=datetime(2026, 1, 15),
    )
    return model_dir


def _sample_request() -> NoShowPredictionRequest:
    return NoShowPredictionRequest(
        appointment_type="maintenance",
        channel="web",
        lead_time_days=21,
        estimated_duration_minutes=75,
        is_first_service_visit=False,
        prior_no_show_count_at_booking=1,
        prior_completed_appointments_at_booking=2,
        reminder_count=1,
        scheduled_day_of_week=2,
        scheduled_hour=9,
        days_since_customer_created_at_booking=400,
        vehicle_age_years_at_booking=4,
        customer_distance_miles=24.5,
        customer_loyalty_tier="silver",
        customer_acquisition_channel="organic_search",
        preferred_contact_method="sms",
        marketing_opt_in=True,
    )


def test_no_show_feature_schema_excludes_known_target_leakage() -> None:
    assert inspect_features_for_target_leakage(FEATURE_COLUMNS) == []

    with pytest.raises(ValueError, match="Target leakage"):
        validate_no_target_leakage((*FEATURE_COLUMNS, "completed_at"))


def test_training_serializes_model_schema_metadata_and_metrics(
    trained_model_dir: Path,
    small_training_frame: tuple[pd.DataFrame, pd.Series],
) -> None:
    features, _target = small_training_frame
    loaded = load_model_artifact(trained_model_dir)

    assert (trained_model_dir / MODEL_FILENAME).exists()
    assert (trained_model_dir / METADATA_FILENAME).exists()
    assert (trained_model_dir / METRICS_FILENAME).exists()
    assert (trained_model_dir / FEATURE_SCHEMA_FILENAME).exists()
    assert loaded.metadata["selected_model"] in {
        "logistic_regression_baseline",
        "hist_gradient_boosting",
    }
    assert "roc_auc" in loaded.metrics["test"]
    assert "brier_score" in loaded.metrics["test"]
    assert loaded.metrics["test"]["threshold_analysis"]
    prediction = loaded.model.predict_proba(features.head(1))[0, 1]
    assert 0 <= prediction <= 1


def test_risk_tiers_are_monotonic() -> None:
    assert risk_tier_for_probability(0.01) == RiskTier.LOW
    assert risk_tier_for_probability(0.12) == RiskTier.MEDIUM
    assert risk_tier_for_probability(0.24) == RiskTier.HIGH
    assert risk_tier_for_probability(0.50) == RiskTier.VERY_HIGH


def test_threshold_analysis_reports_operational_tradeoffs() -> None:
    rows = threshold_analysis(
        y_true=np.array([0, 0, 1, 1]),
        probabilities=np.array([0.05, 0.18, 0.22, 0.80]),
        thresholds=(0.10, 0.20, 0.50),
    )

    assert [row["threshold"] for row in rows] == [0.10, 0.20, 0.50]
    assert rows[0]["recall"] >= rows[-1]["recall"]
    assert rows[0]["flag_rate"] >= rows[-1]["flag_rate"]


def test_prediction_service_returns_probability_risk_and_model_version(
    trained_model_dir: Path,
) -> None:
    service = NoShowPredictionService.from_model_dir(str(trained_model_dir), "ignored")

    response = service.predict(_sample_request())

    assert 0 <= response.probability <= 1
    assert response.risk_tier in set(RiskTier)
    assert response.model_version == "test-no-show-v1"


def test_no_show_prediction_endpoint(trained_model_dir: Path) -> None:
    get_cached_no_show_prediction_service.cache_clear()
    app = create_app(
        Settings(
            environment="test",
            no_show_model_dir=str(trained_model_dir),
            no_show_model_version="test-no-show-v1",
        ),
    )
    client = TestClient(app)

    response = client.post("/ml/no-show/predict", json=_sample_request().model_dump())

    assert response.status_code == 200
    payload = response.json()
    assert 0 <= payload["probability"] <= 1
    assert payload["risk_tier"] in {tier.value for tier in RiskTier}
    assert payload["model_version"] == "test-no-show-v1"
