from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from app.observability.metrics import record_cache_request

if TYPE_CHECKING:
    from app.core.config import Settings

autocomplete_logger = logging.getLogger("app.autocomplete")
_WHITESPACE_PATTERN = re.compile(r"\s+")
AUTOCOMPLETE_RANKING_FORMULA = (
    "final_score = 0.8 * normalized_lexical + 0.2 * normalized_popularity"
)


@dataclass(frozen=True, slots=True)
class AutocompleteParams:
    query: str
    limit: int


@dataclass(frozen=True, slots=True)
class AutocompleteSuggestion:
    id: int
    sku: str
    title: str
    brand: str
    category: str
    availability: bool


@dataclass(frozen=True, slots=True)
class AutocompleteExecution:
    query_id: str
    query: str
    normalized_query: str
    limit: int
    items: list[AutocompleteSuggestion]


@dataclass(frozen=True, slots=True)
class AutocompleteScoreMetadata:
    prefix_quality: float
    lexical_similarity: float
    lexical_score: float
    normalized_lexical_score: float
    normalized_popularity_score: float
    final_score: float


@dataclass(frozen=True, slots=True)
class AutocompleteCandidate:
    id: int
    sku: str
    title: str
    brand: str
    category: str
    inventory_count: int
    popularity_score: Decimal
    score_metadata: AutocompleteScoreMetadata


@dataclass(frozen=True, slots=True)
class AutocompleteConfig:
    default_limit: int = 8
    max_limit: int = 10
    candidate_limit: int = 40
    cache_ttl_seconds: int = 120
    lexical_weight: float = 0.8
    popularity_weight: float = 0.2

    def __post_init__(self) -> None:
        total_weight = self.lexical_weight + self.popularity_weight
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("Autocomplete ranking weights must sum to 1.0")

    @classmethod
    def from_settings(cls, settings: Settings) -> AutocompleteConfig:
        return cls(
            default_limit=settings.autocomplete_default_limit,
            max_limit=settings.autocomplete_max_limit,
            candidate_limit=settings.autocomplete_candidate_limit,
            cache_ttl_seconds=settings.autocomplete_cache_ttl_seconds,
        )


class AutocompleteRepository(Protocol):
    async def fetch_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[AutocompleteCandidate]:
        """Return autocomplete candidates."""


class AutocompleteCache(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None:
        """Return cached autocomplete payload if present."""

    async def set(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        """Store autocomplete payload in cache."""


class ProductAutocompleteService:
    def __init__(
        self,
        repository: AutocompleteRepository,
        *,
        cache: AutocompleteCache | None = None,
        config: AutocompleteConfig | None = None,
        cache_key_builder: Callable[[str, int], str] | None = None,
    ) -> None:
        self._repository = repository
        self._cache = cache
        self._config = config or AutocompleteConfig()
        self._cache_key_builder = cache_key_builder

    async def autocomplete(
        self,
        params: AutocompleteParams,
        *,
        query_id: str,
    ) -> AutocompleteExecution:
        normalized_query = normalize_autocomplete_query(params.query)
        cache_key = self._cache_key(normalized_query, params.limit)
        cache_outcome = "disabled"

        if self._cache is not None:
            try:
                cached_payload = await self._cache.get(cache_key)
            except Exception:
                cache_outcome = "read_error"
                record_cache_request("autocomplete", cache_outcome)
                autocomplete_logger.exception(
                    "autocomplete.cache_read_failed",
                    extra={"query_id": query_id, "normalized_query": normalized_query},
                )
            else:
                if cached_payload is not None:
                    cache_outcome = "hit"
                    record_cache_request("autocomplete", cache_outcome)
                    items = self._deserialize_items(cached_payload)
                    execution = AutocompleteExecution(
                        query_id=query_id,
                        query=params.query,
                        normalized_query=normalized_query,
                        limit=params.limit,
                        items=items,
                    )
                    autocomplete_logger.info(
                        "autocomplete.completed",
                        extra={
                            "query_id": query_id,
                            "normalized_query": normalized_query,
                            "limit": params.limit,
                            "result_count": len(items),
                            "cache_outcome": cache_outcome,
                        },
                    )
                    return execution

                cache_outcome = "miss"
                record_cache_request("autocomplete", cache_outcome)

        candidates = await self._repository.fetch_candidates(
            normalized_query,
            limit=max(params.limit, self._config.candidate_limit),
        )
        ranked_candidates = self._rank_candidates(candidates)
        items = [self._to_suggestion(candidate) for candidate in ranked_candidates[: params.limit]]

        if self._cache is not None:
            payload = self._serialize_items(items)
            try:
                await self._cache.set(
                    cache_key,
                    payload,
                    ttl_seconds=self._config.cache_ttl_seconds,
                )
            except Exception:
                record_cache_request("autocomplete", "write_error")
                autocomplete_logger.exception(
                    "autocomplete.cache_write_failed",
                    extra={"query_id": query_id, "normalized_query": normalized_query},
                )

        autocomplete_logger.info(
            "autocomplete.completed",
            extra={
                "query_id": query_id,
                "normalized_query": normalized_query,
                "limit": params.limit,
                "result_count": len(items),
                "cache_outcome": cache_outcome,
            },
        )
        return AutocompleteExecution(
            query_id=query_id,
            query=params.query,
            normalized_query=normalized_query,
            limit=params.limit,
            items=items,
        )

    def _cache_key(self, normalized_query: str, limit: int) -> str:
        if self._cache_key_builder is None:
            from app.cache.autocomplete import build_autocomplete_cache_key

            return build_autocomplete_cache_key(normalized_query, limit)
        return self._cache_key_builder(normalized_query, limit)

    def _rank_candidates(
        self,
        candidates: list[AutocompleteCandidate],
    ) -> list[AutocompleteCandidate]:
        max_lexical = max(
            (candidate.score_metadata.lexical_score for candidate in candidates),
            default=0.0,
        )
        max_popularity = max(
            (float(candidate.popularity_score) for candidate in candidates),
            default=1.0,
        )
        ranked_candidates: list[AutocompleteCandidate] = []

        for candidate in candidates:
            normalized_lexical_score = (
                candidate.score_metadata.lexical_score / max_lexical if max_lexical > 0.0 else 0.0
            )
            normalized_popularity_score = (
                float(candidate.popularity_score) / max_popularity if max_popularity > 0.0 else 0.0
            )
            final_score = round(
                self._config.lexical_weight * normalized_lexical_score
                + self._config.popularity_weight * normalized_popularity_score,
                6,
            )
            ranked_candidates.append(
                AutocompleteCandidate(
                    id=candidate.id,
                    sku=candidate.sku,
                    title=candidate.title,
                    brand=candidate.brand,
                    category=candidate.category,
                    inventory_count=candidate.inventory_count,
                    popularity_score=candidate.popularity_score,
                    score_metadata=AutocompleteScoreMetadata(
                        prefix_quality=candidate.score_metadata.prefix_quality,
                        lexical_similarity=candidate.score_metadata.lexical_similarity,
                        lexical_score=candidate.score_metadata.lexical_score,
                        normalized_lexical_score=round(normalized_lexical_score, 6),
                        normalized_popularity_score=round(normalized_popularity_score, 6),
                        final_score=final_score,
                    ),
                )
            )

        return sorted(
            ranked_candidates,
            key=lambda item: (
                -item.score_metadata.final_score,
                -item.score_metadata.prefix_quality,
                -item.score_metadata.lexical_similarity,
                -float(item.popularity_score),
                item.id,
            ),
        )

    def _to_suggestion(self, candidate: AutocompleteCandidate) -> AutocompleteSuggestion:
        return AutocompleteSuggestion(
            id=candidate.id,
            sku=candidate.sku,
            title=candidate.title,
            brand=candidate.brand,
            category=candidate.category,
            availability=candidate.inventory_count > 0,
        )

    def _serialize_items(self, items: list[AutocompleteSuggestion]) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": item.id,
                    "sku": item.sku,
                    "title": item.title,
                    "brand": item.brand,
                    "category": item.category,
                    "availability": item.availability,
                }
                for item in items
            ]
        }

    def _deserialize_items(self, payload: Mapping[str, Any]) -> list[AutocompleteSuggestion]:
        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("Cached autocomplete items must be a list")

        suggestions: list[AutocompleteSuggestion] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                raise ValueError("Cached autocomplete item must be an object")

            suggestions.append(
                AutocompleteSuggestion(
                    id=int(raw_item["id"]),
                    sku=str(raw_item["sku"]),
                    title=str(raw_item["title"]),
                    brand=str(raw_item["brand"]),
                    category=str(raw_item["category"]),
                    availability=bool(raw_item["availability"]),
                )
            )
        return suggestions


def normalize_autocomplete_query(query: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", query.strip()).casefold()
