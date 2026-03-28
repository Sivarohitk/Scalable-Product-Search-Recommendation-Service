from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session
from app.api.schemas.recommendations import RecommendationsResponse
from app.core.config import Settings, get_settings
from app.core.request_context import get_request_id
from app.db.recommendations import ProductRecommendationRepository
from app.services.recommendations import (
    ProductRecommendationService,
    RecommendationConfig,
    RecommendationParams,
    RecommendationSourceProductNotFoundError,
)

router = APIRouter(tags=["recommendations"])


class RecommendationQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    limit: int | None = None
    default_limit: int = Field(exclude=True)
    max_limit: int = Field(exclude=True)

    @model_validator(mode="after")
    def validate_limit(self) -> RecommendationQueryParams:
        if self.limit is not None and self.limit > self.max_limit:
            raise ValueError(f"limit must be less than or equal to {self.max_limit}")
        return self

    def to_service_params(self) -> RecommendationParams:
        return RecommendationParams(
            product_id=self.product_id,
            limit=self.limit or self.default_limit,
        )


def get_recommendation_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProductRecommendationService:
    config = RecommendationConfig.from_settings(settings)
    repository = ProductRecommendationRepository(session, config=config)
    return ProductRecommendationService(repository, config=config)


def get_recommendation_query_params(
    settings: Annotated[Settings, Depends(get_settings)],
    product_id: Annotated[int, Path(ge=1)],
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> RecommendationQueryParams:
    try:
        return RecommendationQueryParams(
            product_id=product_id,
            limit=limit,
            default_limit=settings.recommendations_default_limit,
            max_limit=settings.recommendations_max_limit,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.get(
    "/recommendations/{product_id}",
    response_model=RecommendationsResponse,
    summary="Product recommendations",
)
async def get_recommendations(
    params: Annotated[RecommendationQueryParams, Depends(get_recommendation_query_params)],
    recommendation_service: Annotated[
        ProductRecommendationService,
        Depends(get_recommendation_service),
    ],
) -> RecommendationsResponse:
    try:
        execution = await recommendation_service.recommend(
            params.to_service_params(),
            query_id=get_request_id(),
        )
    except RecommendationSourceProductNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Product {exc.product_id} was not found",
        ) from exc

    return RecommendationsResponse.from_execution(execution)
