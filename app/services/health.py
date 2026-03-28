from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.api.schemas.health import (
    DependencyStatusResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.observability.metrics import record_dependency_health_check


@dataclass(frozen=True, slots=True)
class DependencyCheckResult:
    name: str
    ok: bool
    detail: str
    latency_ms: float


class DependencyCheck(Protocol):
    name: str

    async def ping(self) -> DependencyCheckResult:
        """Return the current dependency status."""


class HealthService:
    def __init__(
        self,
        service_name: str,
        environment: str,
        checks: Sequence[DependencyCheck],
    ) -> None:
        self._service_name = service_name
        self._environment = environment
        self._checks = tuple(checks)

    def liveness(self) -> LivenessResponse:
        return LivenessResponse(
            status="ok",
            service=self._service_name,
            environment=self._environment,
        )

    async def readiness(self) -> ReadinessResponse:
        dependencies: list[DependencyStatusResponse] = []
        overall_status: Literal["ok", "degraded"] = "ok"

        for check in self._checks:
            result = await check.ping()
            status: Literal["ok", "degraded"] = "ok" if result.ok else "degraded"
            record_dependency_health_check(result.name, status)
            if not result.ok:
                overall_status = "degraded"

            dependencies.append(
                DependencyStatusResponse(
                    name=result.name,
                    status=status,
                    detail=result.detail,
                    latency_ms=result.latency_ms,
                )
            )

        return ReadinessResponse(
            status=overall_status,
            service=self._service_name,
            environment=self._environment,
            dependencies=dependencies,
        )
