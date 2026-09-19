"""Training, evaluation, and serialization for no-show prediction."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from dealerai_ops.domain.synthetic import DEFAULT_AS_OF, generate_synthetic_dataset
from dealerai_ops.ml.features import (
    NO_SHOW_FEATURE_SCHEMA,
    build_training_frame,
    dataset_fingerprint,
)
from dealerai_ops.ml.risk import RISK_BANDS, threshold_analysis

RANDOM_STATE = 20260811
MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"
METRICS_FILENAME = "metrics.json"
FEATURE_SCHEMA_FILENAME = "feature_schema.json"


class ModelArtifactError(RuntimeError):
    """Raised when a serialized model artifact is missing or unreadable."""


@dataclass(frozen=True)
class NoShowModelArtifact:
    """Serialized sklearn artifact and metadata."""

    model: Any
    feature_schema: dict[str, object]
    metadata: dict[str, object]
    metrics: dict[str, object]


@dataclass(frozen=True)
class TrainedNoShowModel:
    """In-memory training result before persistence."""

    artifact: NoShowModelArtifact
    model_dir: Path


def train_and_serialize_default_model(
    model_dir: str | Path, model_version: str
) -> TrainedNoShowModel:
    """Train and serialize the deterministic local no-show model."""
    dataset = generate_synthetic_dataset()
    features, target = build_training_frame(dataset)
    return train_and_serialize_model(
        features=features,
        target=target,
        model_dir=model_dir,
        model_version=model_version,
        dataset_version="synthetic-dealership-v1",
        dataset_generated_at=DEFAULT_AS_OF,
    )


def train_and_serialize_model(
    features: pd.DataFrame,
    target: pd.Series,
    model_dir: str | Path,
    model_version: str,
    dataset_version: str,
    dataset_generated_at: datetime,
) -> TrainedNoShowModel:
    """Train candidate models, select by probability quality, and write artifacts."""
    if target.nunique() != 2:
        raise ValueError("No-show training requires both positive and negative examples.")

    train_features, holdout_features, train_target, holdout_target = train_test_split(
        features,
        target,
        test_size=0.30,
        stratify=target,
        random_state=RANDOM_STATE,
    )
    validation_features, test_features, validation_target, test_target = train_test_split(
        holdout_features,
        holdout_target,
        test_size=0.50,
        stratify=holdout_target,
        random_state=RANDOM_STATE,
    )

    candidates = {
        "logistic_regression_baseline": _build_logistic_regression_pipeline(),
        "hist_gradient_boosting": _build_hist_gradient_boosting_pipeline(),
    }
    validation_metrics: dict[str, dict[str, object]] = {}
    fitted_models: dict[str, Any] = {}
    for name, pipeline in candidates.items():
        calibrated = CalibratedClassifierCV(estimator=pipeline, method="sigmoid", cv=3)
        calibrated.fit(train_features, train_target)
        probabilities = calibrated.predict_proba(validation_features)[:, 1]
        validation_metrics[name] = evaluate_probabilities(
            validation_target.to_numpy(), probabilities
        )
        fitted_models[name] = calibrated

    selected_name = _select_model(validation_metrics)
    selected_model = fitted_models[selected_name]
    test_probabilities = selected_model.predict_proba(test_features)[:, 1]
    test_metrics = evaluate_probabilities(test_target.to_numpy(), test_probabilities)
    test_metrics["threshold_analysis"] = threshold_analysis(
        test_target.to_numpy(),
        test_probabilities,
    )
    test_metrics["calibration_curve"] = calibration_diagnostics(
        test_target.to_numpy(),
        test_probabilities,
    )

    fingerprint = dataset_fingerprint(features, target, dataset_generated_at)
    trained_at = datetime.now(UTC).isoformat()
    metadata: dict[str, object] = {
        "model_version": model_version,
        "selected_model": selected_name,
        "candidate_models": list(candidates),
        "selection_policy": "lowest validation Brier score, tie-broken by average precision",
        "trained_at": trained_at,
        "dataset_version": dataset_version,
        "dataset_fingerprint": fingerprint,
        "dataset_generated_at": dataset_generated_at.isoformat(),
        "random_state": RANDOM_STATE,
        "train_rows": len(train_features),
        "validation_rows": len(validation_features),
        "test_rows": len(test_features),
        "positive_rate": float(target.mean()),
        "risk_bands": [
            {
                "tier": band.tier.value,
                "min_probability": band.min_probability,
                "max_probability": min(band.max_probability, 1.0),
            }
            for band in RISK_BANDS
        ],
    }
    metrics: dict[str, object] = {
        "validation": validation_metrics,
        "test": test_metrics,
    }
    artifact = NoShowModelArtifact(
        model=selected_model,
        feature_schema=NO_SHOW_FEATURE_SCHEMA.to_dict(),
        metadata=metadata,
        metrics=metrics,
    )
    write_model_artifact(artifact, model_dir)
    return TrainedNoShowModel(artifact=artifact, model_dir=Path(model_dir))


def evaluate_probabilities(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, object]:
    """Evaluate probability predictions at the default operating threshold."""
    predictions = probabilities >= 0.20
    matrix = confusion_matrix(y_true, predictions, labels=[0, 1])
    return {
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "precision_at_0_20": float(precision_score(y_true, predictions, zero_division=0)),
        "recall_at_0_20": float(recall_score(y_true, predictions, zero_division=0)),
        "f1_at_0_20": float(f1_score(y_true, predictions, zero_division=0)),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "confusion_matrix_at_0_20": matrix.tolist(),
    }


def calibration_diagnostics(
    y_true: np.ndarray, probabilities: np.ndarray
) -> list[dict[str, float]]:
    """Return calibration bins for reliability diagnostics."""
    fraction_of_positives, mean_predicted_value = calibration_curve(
        y_true,
        probabilities,
        n_bins=8,
        strategy="quantile",
    )
    return [
        {
            "mean_predicted_probability": float(predicted),
            "observed_no_show_rate": float(observed),
        }
        for observed, predicted in zip(fraction_of_positives, mean_predicted_value, strict=True)
    ]


def write_model_artifact(artifact: NoShowModelArtifact, model_dir: str | Path) -> None:
    """Write model, metrics, metadata, and feature schema artifacts."""
    path = Path(model_dir)
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact.model, path / MODEL_FILENAME)
    _write_json(path / METADATA_FILENAME, artifact.metadata)
    _write_json(path / METRICS_FILENAME, artifact.metrics)
    _write_json(path / FEATURE_SCHEMA_FILENAME, artifact.feature_schema)


def load_model_artifact(model_dir: str | Path) -> NoShowModelArtifact:
    """Load a serialized no-show model artifact from disk."""
    path = Path(model_dir)
    try:
        model = joblib.load(path / MODEL_FILENAME)
        return NoShowModelArtifact(
            model=model,
            feature_schema=_read_json(path / FEATURE_SCHEMA_FILENAME),
            metadata=_read_json(path / METADATA_FILENAME),
            metrics=_read_json(path / METRICS_FILENAME),
        )
    except (
        OSError,
        ValueError,
        EOFError,
        ImportError,
        AttributeError,
        KeyError,
        IndexError,
        json.JSONDecodeError,
    ) as exc:
        raise ModelArtifactError(f"No-show model artifact is unreadable: {path}") from exc


def model_artifact_exists(model_dir: str | Path) -> bool:
    """Return whether all expected no-show artifact files exist."""
    path = Path(model_dir)
    return all(
        (path / filename).exists()
        for filename in (
            MODEL_FILENAME,
            METADATA_FILENAME,
            METRICS_FILENAME,
            FEATURE_SCHEMA_FILENAME,
        )
    )


def _build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ],
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ],
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, list(NO_SHOW_FEATURE_SCHEMA.numeric_features)),
            (
                "categorical",
                categorical_pipeline,
                list(NO_SHOW_FEATURE_SCHEMA.categorical_features),
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=True,
    )


def _build_logistic_regression_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", _build_preprocessor()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1_000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ],
    )


def _build_hist_gradient_boosting_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", _build_preprocessor()),
            (
                "classifier",
                HistGradientBoostingClassifier(
                    learning_rate=0.05,
                    max_iter=180,
                    max_leaf_nodes=15,
                    l2_regularization=0.05,
                    random_state=RANDOM_STATE,
                ),
            ),
        ],
    )


def _select_model(validation_metrics: dict[str, dict[str, object]]) -> str:
    return min(
        validation_metrics,
        key=lambda name: (
            cast(float, validation_metrics[name]["brier_score"]),
            -cast(float, validation_metrics[name]["average_precision"]),
        ),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
