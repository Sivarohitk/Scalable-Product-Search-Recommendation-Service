from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from typing import TYPE_CHECKING, Any, Protocol

from app.observability.metrics import record_fallback
from app.services.embeddings import embed_text, tokenize_embedding_text

if TYPE_CHECKING:
    from app.core.config import Settings

search_logger = logging.getLogger("app.search")
_WHITESPACE_PATTERN = re.compile(r"\s+")
HYBRID_RANKING_FORMULA = (
    "final_fused_score = 0.55 * normalized_lexical "
    "+ 0.25 * normalized_vector "
    "+ 0.12 * normalized_popularity "
    "+ 0.05 * normalized_rating "
    "+ 0.03 * availability_boost"
)


class SearchSort(StrEnum):
    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    POPULARITY = "popularity"
    NEWEST = "newest"


@dataclass(frozen=True, slots=True)
class SearchFilters:
    category: str | None
    brand: str | None
    price_min: Decimal | None
    price_max: Decimal | None
    availability: bool | None


@dataclass(frozen=True, slots=True)
class SearchParams:
    query: str
    page: int | None
    page_size: int | None
    limit: int | None
    offset: int | None
    filters: SearchFilters
    sort: SearchSort
    debug: bool = False

    def resolved_pagination(self) -> ResolvedPagination:
        if self.limit is not None or self.offset is not None:
            limit = self.limit or 20
            offset = self.offset or 0
            page = (offset // limit) + 1
            page_size = limit
            return ResolvedPagination(limit=limit, offset=offset, page=page, page_size=page_size)

        page_size = self.page_size or 20
        page = self.page or 1
        offset = (page - 1) * page_size
        return ResolvedPagination(limit=page_size, offset=offset, page=page, page_size=page_size)


@dataclass(frozen=True, slots=True)
class ResolvedPagination:
    limit: int
    offset: int
    page: int
    page_size: int

    def with_total(self, total: int) -> SearchPagination:
        total_pages = ceil(total / self.page_size) if total else 0
        return SearchPagination(
            total=total,
            limit=self.limit,
            offset=self.offset,
            page=self.page,
            page_size=self.page_size,
            total_pages=total_pages,
        )


@dataclass(frozen=True, slots=True)
class SearchPagination:
    total: int
    limit: int
    offset: int
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class SearchBusinessBoost:
    popularity: float = 0.0
    rating: float = 0.0
    availability: float = 0.0
    total: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchScoreMetadata:
    text_rank: float = 0.0
    trigram_score: float = 0.0
    lexical_score: float = 0.0
    vector_distance: float | None = None
    vector_score: float = 0.0
    normalized_lexical_score: float = 0.0
    normalized_vector_score: float = 0.0
    business_boost: SearchBusinessBoost = field(default_factory=SearchBusinessBoost)
    final_score: float = 0.0
    retrieval_path: str = "lexical"
    fallback_path: str | None = None
    cache_used: bool | None = None


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    id: int
    sku: str
    title: str
    description: str
    category_slug: str
    category_name: str
    brand_slug: str
    brand_name: str
    price: Decimal
    currency: str
    inventory_count: int
    rating: Decimal
    popularity_score: Decimal
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    score_metadata: SearchScoreMetadata


@dataclass(frozen=True, slots=True)
class SearchRequestDebugMetadata:
    retrieval_mode: str
    fallback_path: str | None
    lexical_candidate_count: int
    vector_candidate_count: int
    ranking_formula: str
    cache_used: bool | None = None


@dataclass(frozen=True, slots=True)
class SearchExecution:
    query_id: str
    query: str
    normalized_query: str
    sort: SearchSort
    filters: SearchFilters
    pagination: SearchPagination
    total: int
    items: list[SearchCandidate]
    debug: SearchRequestDebugMetadata | None = None


@dataclass(frozen=True, slots=True)
class SearchConfig:
    semantic_enabled: bool = True
    lexical_candidate_limit: int = 250
    semantic_candidate_limit: int = 150
    vector_similarity_threshold: float = 0.18
    lexical_weight: float = 0.55
    vector_weight: float = 0.25
    popularity_weight: float = 0.12
    rating_weight: float = 0.05
    availability_weight: float = 0.03

    def __post_init__(self) -> None:
        total_weight = (
            self.lexical_weight
            + self.vector_weight
            + self.popularity_weight
            + self.rating_weight
            + self.availability_weight
        )
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("Hybrid ranking weights must sum to 1.0")

    @classmethod
    def from_settings(cls, settings: Settings) -> SearchConfig:
        return cls(
            semantic_enabled=settings.search_semantic_enabled,
            lexical_candidate_limit=settings.search_lexical_candidate_limit,
            semantic_candidate_limit=settings.search_semantic_candidate_limit,
            vector_similarity_threshold=settings.search_vector_similarity_threshold,
            lexical_weight=settings.search_hybrid_lexical_weight,
            vector_weight=settings.search_hybrid_vector_weight,
            popularity_weight=settings.search_hybrid_popularity_weight,
            rating_weight=settings.search_hybrid_rating_weight,
            availability_weight=settings.search_hybrid_availability_weight,
        )


class SearchRepository(Protocol):
    async def fetch_lexical_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        """Return lexical candidates with score metadata."""

    async def fetch_vector_candidates(
        self,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        """Return semantic candidates with vector score metadata."""


class ProductSearchService:
    def __init__(
        self,
        repository: SearchRepository,
        *,
        config: SearchConfig | None = None,
        embedder: Callable[[str], list[float]] = embed_text,
    ) -> None:
        self._repository = repository
        self._config = config or SearchConfig()
        self._embedder = embedder

    async def search(self, params: SearchParams, *, query_id: str) -> SearchExecution:
        normalized_query = normalize_search_query(params.query)
        lexical_candidates = await self._repository.fetch_lexical_candidates(
            normalized_query,
            limit=self._config.lexical_candidate_limit,
        )
        vector_candidates, fallback_path, raw_vector_candidate_count = (
            await self._collect_vector_candidates(
                normalized_query,
                query_id=query_id,
            )
        )
        ranked_candidates = self._rank_candidates(
            lexical_candidates,
            vector_candidates,
            fallback_path=fallback_path,
        )
        filtered_candidates = self._apply_filters(ranked_candidates, params.filters)
        sorted_candidates = self._sort_candidates(filtered_candidates, params.sort)

        resolved_pagination = params.resolved_pagination()
        paginated_items = sorted_candidates[
            resolved_pagination.offset : resolved_pagination.offset + resolved_pagination.limit
        ]
        pagination = resolved_pagination.with_total(len(sorted_candidates))
        retrieval_mode = _retrieval_mode(
            lexical_candidates=lexical_candidates,
            vector_candidates=vector_candidates,
        )
        debug_metadata = (
            SearchRequestDebugMetadata(
                retrieval_mode=retrieval_mode,
                fallback_path=fallback_path,
                lexical_candidate_count=len(lexical_candidates),
                vector_candidate_count=raw_vector_candidate_count,
                ranking_formula=HYBRID_RANKING_FORMULA,
                cache_used=None,
            )
            if params.debug
            else None
        )
        if fallback_path is not None:
            record_fallback("search", fallback_path)

        search_logger.info(
            "search.completed",
            extra={
                "query_id": query_id,
                "normalized_query": normalized_query,
                "candidate_count": len(ranked_candidates),
                "lexical_candidate_count": len(lexical_candidates),
                "vector_candidate_count": raw_vector_candidate_count,
                "strong_vector_candidate_count": len(vector_candidates),
                "result_count": len(sorted_candidates),
                "returned_count": len(paginated_items),
                "sort": params.sort.value,
                "retrieval_mode": retrieval_mode,
                "fallback_path": fallback_path,
            },
        )

        return SearchExecution(
            query_id=query_id,
            query=params.query,
            normalized_query=normalized_query,
            sort=params.sort,
            filters=params.filters,
            pagination=pagination,
            total=len(sorted_candidates),
            items=paginated_items,
            debug=debug_metadata,
        )

    async def _collect_vector_candidates(
        self,
        normalized_query: str,
        *,
        query_id: str,
    ) -> tuple[list[SearchCandidate], str | None, int]:
        if not self._config.semantic_enabled:
            return [], "semantic_disabled", 0

        query_embedding = self._embedder(normalized_query)
        try:
            vector_candidates = await self._repository.fetch_vector_candidates(
                query_embedding,
                limit=self._config.semantic_candidate_limit,
            )
        except Exception:
            search_logger.exception(
                "search.semantic_unavailable",
                extra={"query_id": query_id, "normalized_query": normalized_query},
            )
            return [], "semantic_error", 0

        if not vector_candidates:
            return [], "semantic_empty", 0

        strong_candidates = [
            candidate
            for candidate in vector_candidates
            if self._is_strong_vector_candidate(normalized_query, candidate)
        ]
        if not strong_candidates:
            return [], "semantic_weak", len(vector_candidates)

        return strong_candidates, None, len(vector_candidates)

    def _rank_candidates(
        self,
        lexical_candidates: list[SearchCandidate],
        vector_candidates: list[SearchCandidate],
        *,
        fallback_path: str | None,
    ) -> list[SearchCandidate]:
        lexical_by_id = {candidate.id: candidate for candidate in lexical_candidates}
        vector_by_id = {candidate.id: candidate for candidate in vector_candidates}
        merged_ids = set(lexical_by_id) | set(vector_by_id)

        max_lexical = max(
            (candidate.score_metadata.lexical_score for candidate in lexical_by_id.values()),
            default=0.0,
        )
        max_vector = max(
            (candidate.score_metadata.vector_score for candidate in vector_by_id.values()),
            default=0.0,
        )
        max_popularity = max(
            (
                float(
                    (lexical_by_id.get(candidate_id) or vector_by_id[candidate_id]).popularity_score
                )
                for candidate_id in merged_ids
            ),
            default=1.0,
        )

        ranked_candidates: list[SearchCandidate] = []
        for candidate_id in merged_ids:
            lexical_candidate = lexical_by_id.get(candidate_id)
            vector_candidate = vector_by_id.get(candidate_id)
            base_candidate = lexical_candidate or vector_candidate
            if base_candidate is None:
                continue

            raw_lexical_score = (
                lexical_candidate.score_metadata.lexical_score if lexical_candidate else 0.0
            )
            raw_vector_score = (
                vector_candidate.score_metadata.vector_score if vector_candidate else 0.0
            )
            normalized_lexical_score = (
                raw_lexical_score / max_lexical if max_lexical > 0.0 else 0.0
            )
            normalized_vector_score = raw_vector_score / max_vector if max_vector > 0.0 else 0.0
            business_boost = self._business_boost(base_candidate, max_popularity=max_popularity)
            final_score = round(
                self._config.lexical_weight * normalized_lexical_score
                + self._config.vector_weight * normalized_vector_score
                + business_boost.total,
                6,
            )
            score_metadata = SearchScoreMetadata(
                text_rank=lexical_candidate.score_metadata.text_rank if lexical_candidate else 0.0,
                trigram_score=(
                    lexical_candidate.score_metadata.trigram_score if lexical_candidate else 0.0
                ),
                lexical_score=raw_lexical_score,
                vector_distance=(
                    vector_candidate.score_metadata.vector_distance if vector_candidate else None
                ),
                vector_score=raw_vector_score,
                normalized_lexical_score=round(normalized_lexical_score, 6),
                normalized_vector_score=round(normalized_vector_score, 6),
                business_boost=business_boost,
                final_score=final_score,
                retrieval_path=_retrieval_path(
                    has_lexical=lexical_candidate is not None,
                    has_vector=vector_candidate is not None,
                ),
                fallback_path=fallback_path,
                cache_used=None,
            )
            ranked_candidates.append(replace(base_candidate, score_metadata=score_metadata))

        return ranked_candidates

    def _business_boost(
        self,
        candidate: SearchCandidate,
        *,
        max_popularity: float,
    ) -> SearchBusinessBoost:
        normalized_popularity = (
            float(candidate.popularity_score) / max_popularity if max_popularity > 0.0 else 0.0
        )
        popularity_component = round(
            normalized_popularity * self._config.popularity_weight,
            6,
        )
        rating_component = round(
            (float(candidate.rating) / 5.0) * self._config.rating_weight,
            6,
        )
        availability_component = round(
            self._config.availability_weight if candidate.inventory_count > 0 else 0.0,
            6,
        )
        return SearchBusinessBoost(
            popularity=popularity_component,
            rating=rating_component,
            availability=availability_component,
            total=round(
                popularity_component + rating_component + availability_component,
                6,
            ),
        )

    def _is_strong_vector_candidate(
        self,
        normalized_query: str,
        candidate: SearchCandidate,
    ) -> bool:
        if candidate.score_metadata.vector_score < self._config.vector_similarity_threshold:
            return False

        query_tokens = set(tokenize_embedding_text(normalized_query))
        candidate_tokens = set(
            tokenize_embedding_text(
                " ".join(
                    [
                        candidate.brand_name,
                        candidate.category_name,
                        candidate.title,
                        candidate.description,
                    ]
                )
            )
        )
        return bool(query_tokens & candidate_tokens)

    def _apply_filters(
        self,
        candidates: list[SearchCandidate],
        filters: SearchFilters,
    ) -> list[SearchCandidate]:
        filtered: list[SearchCandidate] = []

        for candidate in candidates:
            if filters.category and not _matches_term(
                filters.category,
                candidate.category_slug,
                candidate.category_name,
            ):
                continue
            if filters.brand and not _matches_term(
                filters.brand,
                candidate.brand_slug,
                candidate.brand_name,
            ):
                continue
            if filters.price_min is not None and candidate.price < filters.price_min:
                continue
            if filters.price_max is not None and candidate.price > filters.price_max:
                continue
            if filters.availability is True and candidate.inventory_count <= 0:
                continue
            if filters.availability is False and candidate.inventory_count > 0:
                continue
            filtered.append(candidate)

        return filtered

    def _sort_candidates(
        self,
        candidates: list[SearchCandidate],
        sort: SearchSort,
    ) -> list[SearchCandidate]:
        if sort is SearchSort.PRICE_ASC:
            return sorted(
                candidates,
                key=lambda item: (item.price, -item.score_metadata.final_score, item.id),
            )
        if sort is SearchSort.PRICE_DESC:
            return sorted(
                candidates,
                key=lambda item: (-float(item.price), -item.score_metadata.final_score, item.id),
            )
        if sort is SearchSort.POPULARITY:
            return sorted(
                candidates,
                key=lambda item: (
                    -float(item.popularity_score),
                    -item.score_metadata.final_score,
                    item.id,
                ),
            )
        if sort is SearchSort.NEWEST:
            return sorted(
                candidates,
                key=lambda item: (
                    -item.created_at.timestamp(),
                    -item.score_metadata.final_score,
                    item.id,
                ),
            )
        return sorted(
            candidates,
            key=lambda item: (
                -item.score_metadata.final_score,
                -item.score_metadata.lexical_score,
                -item.score_metadata.vector_score,
                -float(item.popularity_score),
                item.id,
            ),
        )


def normalize_search_query(query: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", query.strip()).casefold()


def normalize_filter_term(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value.strip()).casefold()


def _matches_term(expected: str, slug: str, name: str) -> bool:
    normalized_slug = normalize_filter_term(slug)
    normalized_name = normalize_filter_term(name)
    return expected == normalized_slug or expected == normalized_name


def _retrieval_path(*, has_lexical: bool, has_vector: bool) -> str:
    if has_lexical and has_vector:
        return "lexical+vector"
    if has_vector:
        return "vector"
    return "lexical"


def _retrieval_mode(
    *,
    lexical_candidates: list[SearchCandidate],
    vector_candidates: list[SearchCandidate],
) -> str:
    if lexical_candidates and vector_candidates:
        return "hybrid"
    if vector_candidates:
        return "semantic_only"
    return "lexical_only"
