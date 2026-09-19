"""Prediction service for appointment no-show risk."""

from functools import lru_cache

from dealerai_ops.ml.features import frame_from_prediction_request
from dealerai_ops.ml.risk import risk_tier_for_probability
from dealerai_ops.ml.schemas import NoShowPredictionRequest, NoShowPredictionResponse
from dealerai_ops.ml.training import (
    NoShowModelArtifact,
    load_model_artifact,
    model_artifact_exists,
    train_and_serialize_default_model,
)
from dealerai_ops.observability import start_span


class NoShowPredictionService:
    """Load a serialized sklearn model and produce structured predictions."""

    def __init__(self, artifact: NoShowModelArtifact) -> None:
        self.artifact = artifact

    @classmethod
    def from_model_dir(cls, model_dir: str, model_version: str) -> "NoShowPredictionService":
        """Load the configured model, training a deterministic local artifact if needed."""
        if not model_artifact_exists(model_dir):
            train_and_serialize_default_model(model_dir=model_dir, model_version=model_version)
        return cls(load_model_artifact(model_dir))

    def predict(self, request: NoShowPredictionRequest) -> NoShowPredictionResponse:
        """Return no-show probability and risk tier."""
        metadata_model_version = self.artifact.metadata.get("model_version")
        model_version = (
            metadata_model_version if isinstance(metadata_model_version, str) else "unknown"
        )
        with start_span(
            "model_inference",
            attributes={
                "model_family": "no_show_prediction",
                "model_version": model_version,
                "feature_count": len(NoShowPredictionRequest.model_fields),
            },
        ) as span:
            features = frame_from_prediction_request(request)
            probability = float(self.artifact.model.predict_proba(features)[0, 1])
            risk_tier = risk_tier_for_probability(probability)
            span.set_attributes(
                {
                    "probability": probability,
                    "risk_tier": risk_tier.value,
                    "model_version": model_version,
                }
            )
            return NoShowPredictionResponse(
                probability=probability,
                risk_tier=risk_tier,
                model_version=model_version,
            )


@lru_cache(maxsize=4)
def get_cached_no_show_prediction_service(
    model_dir: str,
    model_version: str,
) -> NoShowPredictionService:
    """Return a cached prediction service for the configured artifact path."""
    return NoShowPredictionService.from_model_dir(model_dir, model_version)
