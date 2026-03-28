from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.health import get_health_service
from app.api.schemas.health import (
    DependencyStatusResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.main import create_app


class StubHealthService:
    def __init__(self, status: str) -> None:
        self._status = status

    def liveness(self) -> LivenessResponse:
        return LivenessResponse(
            status="ok",
            service="stub-service",
            environment="test",
        )

    async def readiness(self) -> ReadinessResponse:
        dependency_status = "ok" if self._status == "ok" else "degraded"
        return ReadinessResponse(
            status=self._status,
            service="stub-service",
            environment="test",
            dependencies=[
                DependencyStatusResponse(
                    name="postgres",
                    status=dependency_status,
                    detail=dependency_status,
                    latency_ms=1.0,
                ),
                DependencyStatusResponse(
                    name="redis",
                    status=dependency_status,
                    detail=dependency_status,
                    latency_ms=1.0,
                ),
            ],
        )


def test_liveness_endpoint_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.json()["status"] == "ok"
    assert "service" in response.json()
    assert "environment" in response.json()


def test_readiness_endpoint_returns_ok_when_dependencies_pass() -> None:
    app = create_test_app(StubHealthService(status="ok"))

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_endpoint_returns_503_when_dependencies_degrade() -> None:
    app = create_test_app(StubHealthService(status="degraded"))

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def create_test_app(health_service: StubHealthService) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: health_service
    return app

