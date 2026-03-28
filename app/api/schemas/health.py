from typing import Literal

from pydantic import BaseModel, Field


class DependencyStatusResponse(BaseModel):
    name: str
    status: Literal["ok", "degraded"]
    detail: str
    latency_ms: float = Field(ge=0)


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    environment: str
    dependencies: list[DependencyStatusResponse]

