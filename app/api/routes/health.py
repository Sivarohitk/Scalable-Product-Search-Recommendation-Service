from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])


def get_health_service(request: Request) -> HealthService:
    return cast(HealthService, request.app.state.health_service)


@router.get("/health/live", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> LivenessResponse:
    return health_service.liveness()


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> ReadinessResponse | JSONResponse:
    readiness_response = await health_service.readiness()
    if readiness_response.status == "degraded":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=readiness_response.model_dump(mode="json"),
        )
    return readiness_response
