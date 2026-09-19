"""Machine learning inference endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from dealerai_ops.core.config import Settings, get_settings
from dealerai_ops.ml.schemas import NoShowPredictionRequest, NoShowPredictionResponse
from dealerai_ops.ml.service import (
    NoShowPredictionService,
    get_cached_no_show_prediction_service,
)
from dealerai_ops.ml.training import ModelArtifactError

router = APIRouter(prefix="/ml", tags=["ml"])


def _settings_from_request(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


SettingsDependency = Annotated[Settings, Depends(_settings_from_request)]


def get_no_show_prediction_service(settings: SettingsDependency) -> NoShowPredictionService:
    """Load the configured no-show prediction service."""
    try:
        return get_cached_no_show_prediction_service(
            settings.no_show_model_dir,
            settings.no_show_model_version,
        )
    except ModelArtifactError as exc:
        raise HTTPException(status_code=503, detail="No-show model is unavailable.") from exc


NoShowServiceDependency = Annotated[
    NoShowPredictionService,
    Depends(get_no_show_prediction_service),
]


@router.post("/no-show/predict", response_model=NoShowPredictionResponse)
def predict_no_show(
    request: NoShowPredictionRequest,
    service: NoShowServiceDependency,
) -> NoShowPredictionResponse:
    """Predict appointment no-show probability."""
    return service.predict(request)
