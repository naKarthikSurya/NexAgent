"""HTTP response schemas for the FastAPI foundation."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned by the service health endpoint."""

    status: str
    environment: str


class ErrorResponse(BaseModel):
    """Common shape reserved for API error responses."""

    detail: str
