from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.services.search import SearchExecution, SearchFilters, SearchSort


class SearchFacetResponse(BaseModel):
    slug: str
    name: str


class SearchProductResponse(BaseModel):
    id: int
    sku: str
    title: str
    description: str
    category: SearchFacetResponse
    brand: SearchFacetResponse
    price: float
    currency: str
    inventory_count: int
    availability: bool
    rating: float
    popularity_score: float
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    debug: SearchProductDebugResponse | None = None


class SearchPaginationResponse(BaseModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class SearchFiltersResponse(BaseModel):
    category: str | None
    brand: str | None
    price_min: float | None
    price_max: float | None
    availability: bool | None


class SearchBusinessBoostDebugResponse(BaseModel):
    popularity: float
    rating: float
    availability: float
    total: float


class SearchProductDebugResponse(BaseModel):
    lexical_score: float
    vector_score: float
    business_boost: SearchBusinessBoostDebugResponse
    final_fused_score: float
    retrieval_path: str
    fallback_path: str | None
    cache_used: bool | None


class SearchDebugResponse(BaseModel):
    retrieval_mode: str
    fallback_path: str | None
    lexical_candidate_count: int = Field(ge=0)
    vector_candidate_count: int = Field(ge=0)
    ranking_formula: str
    cache_used: bool | None


class SearchResponse(BaseModel):
    query_id: str
    query: str
    normalized_query: str
    sort: SearchSort
    filters: SearchFiltersResponse
    pagination: SearchPaginationResponse
    items: list[SearchProductResponse]
    debug: SearchDebugResponse | None = None

    @classmethod
    def from_execution(cls, execution: SearchExecution) -> SearchResponse:
        return cls(
            query_id=execution.query_id,
            query=execution.query,
            normalized_query=execution.normalized_query,
            sort=execution.sort,
            filters=_filters_response(execution.filters),
            pagination=SearchPaginationResponse(
                total=execution.total,
                limit=execution.pagination.limit,
                offset=execution.pagination.offset,
                page=execution.pagination.page,
                page_size=execution.pagination.page_size,
                total_pages=execution.pagination.total_pages,
            ),
            items=[
                SearchProductResponse(
                    id=item.id,
                    sku=item.sku,
                    title=item.title,
                    description=item.description,
                    category=SearchFacetResponse(
                        slug=item.category_slug,
                        name=item.category_name,
                    ),
                    brand=SearchFacetResponse(
                        slug=item.brand_slug,
                        name=item.brand_name,
                    ),
                    price=float(item.price),
                    currency=item.currency,
                    inventory_count=item.inventory_count,
                    availability=item.inventory_count > 0,
                    rating=float(item.rating),
                    popularity_score=float(item.popularity_score),
                    attributes=item.attributes,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    debug=_product_debug_response(item, enabled=execution.debug is not None),
                )
                for item in execution.items
            ],
            debug=(
                SearchDebugResponse(
                    retrieval_mode=execution.debug.retrieval_mode,
                    fallback_path=execution.debug.fallback_path,
                    lexical_candidate_count=execution.debug.lexical_candidate_count,
                    vector_candidate_count=execution.debug.vector_candidate_count,
                    ranking_formula=execution.debug.ranking_formula,
                    cache_used=execution.debug.cache_used,
                )
                if execution.debug is not None
                else None
            ),
        )


def _filters_response(filters: SearchFilters) -> SearchFiltersResponse:
    return SearchFiltersResponse(
        category=filters.category,
        brand=filters.brand,
        price_min=float(filters.price_min) if filters.price_min is not None else None,
        price_max=float(filters.price_max) if filters.price_max is not None else None,
        availability=filters.availability,
    )


def _product_debug_response(
    item: Any,
    *,
    enabled: bool,
) -> SearchProductDebugResponse | None:
    if not enabled:
        return None

    return SearchProductDebugResponse(
        lexical_score=item.score_metadata.lexical_score,
        vector_score=item.score_metadata.vector_score,
        business_boost=SearchBusinessBoostDebugResponse(
            popularity=item.score_metadata.business_boost.popularity,
            rating=item.score_metadata.business_boost.rating,
            availability=item.score_metadata.business_boost.availability,
            total=item.score_metadata.business_boost.total,
        ),
        final_fused_score=item.score_metadata.final_score,
        retrieval_path=item.score_metadata.retrieval_path,
        fallback_path=item.score_metadata.fallback_path,
        cache_used=item.score_metadata.cache_used,
    )
