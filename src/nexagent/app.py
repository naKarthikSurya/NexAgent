"""FastAPI application factory."""

from fastapi import FastAPI

from nexagent.config import Settings, get_settings
from nexagent.schemas import HealthResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a configured local NexAgent API application."""

    app_settings = settings or get_settings()
    app = FastAPI(
        title="NexAgent",
        version="0.1.0",
        debug=app_settings.debug,
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", environment=app_settings.environment)

    return app
