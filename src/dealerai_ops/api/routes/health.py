"""Health and readiness endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dealerai_ops.core.config import Settings, get_settings
from dealerai_ops.db.session import check_database_connection

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Basic process health response."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness response with dependency checks."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, bool] = Field(default_factory=dict)


def _settings_from_request(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


SettingsDependency = Annotated[Settings, Depends(_settings_from_request)]


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDependency) -> HealthResponse:
    """Return process-level health."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready(settings: SettingsDependency) -> ReadinessResponse | JSONResponse:
    """Return readiness based on required dependency checks."""
    checks = {"database": check_database_connection(settings.database_url)}
    if all(checks.values()):
        return ReadinessResponse(status="ready", checks=checks)

    response = ReadinessResponse(status="not_ready", checks=checks)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )
