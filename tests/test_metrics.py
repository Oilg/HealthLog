"""Tests for /metrics endpoint (Prometheus instrumentation)."""

import pytest
from fastapi.testclient import TestClient

from health_log.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_metrics_endpoint_exists(client: TestClient) -> None:
    """GET /metrics should return 200."""
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_content_type(client: TestClient) -> None:
    """Response should be Prometheus text format."""
    response = client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]


def test_metrics_contains_http_requests_total(client: TestClient) -> None:
    """After a request, http_requests_total must appear in metrics."""
    client.get("/docs")
    response = client.get("/metrics")
    assert "http_requests_total" in response.text


def test_metrics_contains_duration_histogram(client: TestClient) -> None:
    """Latency histogram must be present."""
    response = client.get("/metrics")
    assert "http_request_duration_seconds" in response.text


def test_metrics_not_in_openapi_schema(client: TestClient) -> None:
    """/metrics should be excluded from OpenAPI docs UI (include_in_schema=False)."""
    app = create_app()
    metrics_routes = [
        r for r in app.routes
        if hasattr(r, "path") and r.path == "/metrics" and getattr(r, "include_in_schema", True)
    ]
    assert metrics_routes == [], "/metrics route should have include_in_schema=False"
