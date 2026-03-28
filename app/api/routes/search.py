from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session
from app.api.schemas.search import SearchResponse
from app.core.config import Settings, get_settings
from app.core.request_context import get_request_id
from app.db.search import ProductSearchRepository
from app.services.search import (
    ProductSearchService,
    SearchConfig,
    SearchFilters,
    SearchParams,
    SearchSort,
    normalize_filter_term,
)

router = APIRouter(tags=["search"])


class SearchQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    page: int | None = None
    page_size: int | None = None
    limit: int | None = None
    offset: int | None = None
    category: str | None = None
    brand: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    availability: bool | None = None
    sort: SearchSort = SearchSort.RELEVANCE
    debug: bool = False

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value

    @field_validator("category", "brand")
    @classmethod
    def normalize_terms(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_filter_term(value)
        if not normalized:
            raise ValueError("filter values must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_ranges(self) -> SearchQueryParams:
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must be less than or equal to price_max")

        uses_page_pagination = self.page is not None or self.page_size is not None
        uses_offset_pagination = self.limit is not None or self.offset is not None
        if uses_page_pagination and uses_offset_pagination:
            raise ValueError("use either page/page_size or limit/offset, not both")

        return self

    def to_service_params(self) -> SearchParams:
        return SearchParams(
            query=self.query,
            page=self.page,
            page_size=self.page_size,
            limit=self.limit,
            offset=self.offset,
            filters=SearchFilters(
                category=self.category,
                brand=self.brand,
                price_min=self.price_min,
                price_max=self.price_max,
                availability=self.availability,
            ),
            sort=self.sort,
            debug=self.debug,
        )
def get_search_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProductSearchService:
    repository = ProductSearchRepository(session)
    return ProductSearchService(
        repository,
        config=SearchConfig.from_settings(settings),
    )


def get_search_query_params(
    query: Annotated[str, Query(min_length=1, max_length=200)],
    page: Annotated[int | None, Query(ge=1)] = None,
    page_size: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int | None, Query(ge=0)] = None,
    category: Annotated[str | None, Query(max_length=128)] = None,
    brand: Annotated[str | None, Query(max_length=128)] = None,
    price_min: Annotated[Decimal | None, Query(ge=0)] = None,
    price_max: Annotated[Decimal | None, Query(ge=0)] = None,
    availability: bool | None = None,
    sort: SearchSort = SearchSort.RELEVANCE,
    debug: bool = False,
) -> SearchQueryParams:
    try:
        return SearchQueryParams(
            query=query,
            page=page,
            page_size=page_size,
            limit=limit,
            offset=offset,
            category=category,
            brand=brand,
            price_min=price_min,
            price_max=price_max,
            availability=availability,
            sort=sort,
            debug=debug,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.get("/search", response_model=SearchResponse, summary="Hybrid product search")
async def search_products(
    params: Annotated[SearchQueryParams, Depends(get_search_query_params)],
    search_service: Annotated[ProductSearchService, Depends(get_search_service)],
) -> SearchResponse:
    execution = await search_service.search(
        params.to_service_params(),
        query_id=get_request_id(),
    )
    return SearchResponse.from_execution(execution)
