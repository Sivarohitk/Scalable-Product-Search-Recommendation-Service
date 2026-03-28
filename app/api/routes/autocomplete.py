from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_redis_client
from app.api.schemas.autocomplete import AutocompleteResponse
from app.cache.autocomplete import RedisAutocompleteCache
from app.core.config import Settings, get_settings
from app.core.request_context import get_request_id
from app.db.autocomplete import ProductAutocompleteRepository
from app.services.autocomplete import (
    AutocompleteConfig,
    AutocompleteParams,
    ProductAutocompleteService,
)

router = APIRouter(tags=["autocomplete"])


class AutocompleteQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    limit: int | None = None
    default_limit: int = Field(exclude=True)
    max_limit: int = Field(exclude=True)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value

    @model_validator(mode="after")
    def validate_limit(self) -> AutocompleteQueryParams:
        if self.limit is not None and self.limit > self.max_limit:
            raise ValueError(f"limit must be less than or equal to {self.max_limit}")
        return self

    def to_service_params(self) -> AutocompleteParams:
        return AutocompleteParams(
            query=self.query,
            limit=self.limit or self.default_limit,
        )


def get_autocomplete_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    redis_client: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProductAutocompleteService:
    repository = ProductAutocompleteRepository(session)
    cache = RedisAutocompleteCache(redis_client)
    return ProductAutocompleteService(
        repository,
        cache=cache,
        config=AutocompleteConfig.from_settings(settings),
    )


def get_autocomplete_query_params(
    settings: Annotated[Settings, Depends(get_settings)],
    query: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> AutocompleteQueryParams:
    try:
        return AutocompleteQueryParams(
            query=query,
            limit=limit,
            default_limit=settings.autocomplete_default_limit,
            max_limit=settings.autocomplete_max_limit,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.get("/autocomplete", response_model=AutocompleteResponse, summary="Product autocomplete")
async def autocomplete_products(
    params: Annotated[AutocompleteQueryParams, Depends(get_autocomplete_query_params)],
    autocomplete_service: Annotated[
        ProductAutocompleteService,
        Depends(get_autocomplete_service),
    ],
) -> AutocompleteResponse:
    execution = await autocomplete_service.autocomplete(
        params.to_service_params(),
        query_id=get_request_id(),
    )
    return AutocompleteResponse.from_execution(execution)
