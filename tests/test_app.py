"""Tests for the FastAPI application foundation."""

from fastapi.testclient import TestClient

from nexagent.app import create_app
from nexagent.config import Settings


def test_health_endpoint_returns_service_status() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_application_exposes_openapi_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "NexAgent"
