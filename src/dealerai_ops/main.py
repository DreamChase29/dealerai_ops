"""FastAPI application entrypoint."""

from fastapi import FastAPI

from dealerai_ops.api.routes.agent import router as agent_router
from dealerai_ops.api.routes.escalations import router as escalations_router
from dealerai_ops.api.routes.health import router as health_router
from dealerai_ops.api.routes.ml import router as ml_router
from dealerai_ops.core.config import Settings, get_settings
from dealerai_ops.core.logging import configure_logging
from dealerai_ops.observability import configure_observability


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    configure_observability(app_settings)

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = app_settings
    app.include_router(agent_router)
    app.include_router(escalations_router)
    app.include_router(health_router)
    app.include_router(ml_router)
    return app


app = create_app()
