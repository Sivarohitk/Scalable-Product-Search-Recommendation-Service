from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.health import get_health_service
from app.api.schemas.health import (
    DependencyStatusResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.main import create_app
from app.observability.metrics import record_cache_request, record_fallback


class StubHealthService:
    def liveness(self) -> LivenessResponse:
        return LivenessResponse(
            status="ok",
            service="stub-service",
            environment="test",
        )

    async def readiness(self) -> ReadinessResponse:
        return ReadinessResponse(
            status="ok",
            service="stub-service",
            environment="test",
            dependencies=[
                DependencyStatusResponse(
                    name="postgres",
                    status="ok",
                    detail="ok",
                    latency_ms=1.0,
                ),
                DependencyStatusResponse(
                    name="redis",
                    status="ok",
                    detail="ok",
                    latency_ms=1.0,
                ),
            ],
        )


def test_metrics_endpoint_exposes_prometheus_payload() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/missing-route").status_code == 404
        record_cache_request("autocomplete", "hit")
        record_fallback("search", "semantic_weak")
        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "product_search_http_requests_total" in metrics_response.text
    assert "product_search_http_errors_total" in metrics_response.text
    assert "product_search_dependency_health_checks_total" in metrics_response.text
    assert "product_search_cache_requests_total" in metrics_response.text
    assert "product_search_fallbacks_total" in metrics_response.text


def create_test_app() -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_health_service] = StubHealthService
    return app
