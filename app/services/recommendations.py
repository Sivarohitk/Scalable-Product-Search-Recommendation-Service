from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.observability.metrics import record_fallback

if TYPE_CHECKING:
    from app.core.config import Settings

recommendation_logger = logging.getLogger("app.recommendations")


class RecommendationStrategy(StrEnum):
    COOCCURRENCE = "cooccurrence"
    CONTENT_BASED = "content_based"
    POPULARITY_IN_CATEGORY = "popularity_in_category"
    GLOBAL_POPULARITY = "global_popularity"
    FALLBACK_CHAIN = "fallback_chain"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class RecommendationParams:
    product_id: int
    limit: int


@dataclass(frozen=True, slots=True)
class RecommendationSourceProduct:
    id: int
    category_id: int
    brand_id: int
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class RecommendationCandidate:
    id: int
    sku: str
    title: str
    brand: str
    category: str
    price: Decimal
    currency: str
    inventory_count: int
    rating: Decimal
    popularity_score: Decimal


@dataclass(frozen=True, slots=True)
class RecommendationProduct:
    id: int
    sku: str
    title: str
    brand: str
    category: str
    price: Decimal
    currency: str
    availability: bool
    rating: Decimal
    popularity_score: Decimal


@dataclass(frozen=True, slots=True)
class RecommendationExecution:
    query_id: str
    source_product_id: int
    limit: int
    strategy_used: RecommendationStrategy
    strategy_path: list[RecommendationStrategy]
    items: list[RecommendationProduct]


@dataclass(frozen=True, slots=True)
class RecommendationConfig:
    default_limit: int = 6
    max_limit: int = 12
    stage_candidate_limit: int = 24
    content_category_bonus: float = 0.08
    content_brand_bonus: float = 0.05
    co_purchase_weight: float = 1.35

    @classmethod
    def from_settings(cls, settings: Settings) -> RecommendationConfig:
        return cls(
            default_limit=settings.recommendations_default_limit,
            max_limit=settings.recommendations_max_limit,
            stage_candidate_limit=settings.recommendations_candidate_limit,
        )


class RecommendationSourceProductNotFoundError(LookupError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"Product {product_id} not found")
        self.product_id = product_id


class RecommendationRepository(Protocol):
    async def fetch_source_product(
        self,
        product_id: int,
    ) -> RecommendationSourceProduct | None:
        """Return the source product used to seed recommendations."""

    async def fetch_cooccurrence_candidates(
        self,
        source_product_id: int,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        """Return co-occurrence recommendations."""

    async def fetch_content_based_candidates(
        self,
        source_product: RecommendationSourceProduct,
        *,
        exclude_ids: set[int],
        limit: int,
        category_bonus: float,
        brand_bonus: float,
    ) -> list[RecommendationCandidate]:
        """Return content-based fallback recommendations."""

    async def fetch_category_popularity_candidates(
        self,
        category_id: int,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        """Return category popularity fallback recommendations."""

    async def fetch_global_popularity_candidates(
        self,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        """Return global popularity fallback recommendations."""


class ProductRecommendationService:
    def __init__(
        self,
        repository: RecommendationRepository,
        *,
        config: RecommendationConfig | None = None,
    ) -> None:
        self._repository = repository
        self._config = config or RecommendationConfig()

    async def recommend(
        self,
        params: RecommendationParams,
        *,
        query_id: str,
    ) -> RecommendationExecution:
        source_product = await self._repository.fetch_source_product(params.product_id)
        if source_product is None:
            raise RecommendationSourceProductNotFoundError(params.product_id)

        selected_ids = {source_product.id}
        items: list[RecommendationProduct] = []
        strategy_path: list[RecommendationStrategy] = []
        attempted_strategies: list[RecommendationStrategy] = []

        for strategy, loader in self._strategy_loaders(source_product):
            if len(items) >= params.limit:
                break

            attempted_strategies.append(strategy)
            remaining = params.limit - len(items)
            stage_limit = max(remaining, self._config.stage_candidate_limit)

            try:
                candidates = await loader(selected_ids, stage_limit)
            except Exception:
                recommendation_logger.exception(
                    "recommendations.stage_failed",
                    extra={
                        "query_id": query_id,
                        "source_product_id": source_product.id,
                        "strategy_used": strategy.value,
                    },
                )
                continue

            added_any = False
            for candidate in candidates:
                if candidate.id in selected_ids:
                    continue

                selected_ids.add(candidate.id)
                items.append(self._to_product(candidate))
                added_any = True
                if len(items) >= params.limit:
                    break

            if added_any:
                strategy_path.append(strategy)

        strategy_used = _strategy_used(strategy_path)
        fallback_metric_path = _fallback_metric_path(strategy_path)
        if fallback_metric_path is not None:
            record_fallback("recommendations", fallback_metric_path)
        recommendation_logger.info(
            "recommendations.completed",
            extra={
                "query_id": query_id,
                "source_product_id": source_product.id,
                "strategy_used": strategy_used.value,
                "strategy_path": ">".join(strategy.value for strategy in strategy_path),
                "attempted_strategies": ">".join(
                    strategy.value for strategy in attempted_strategies
                ),
                "limit": params.limit,
                "result_count": len(items),
            },
        )
        return RecommendationExecution(
            query_id=query_id,
            source_product_id=source_product.id,
            limit=params.limit,
            strategy_used=strategy_used,
            strategy_path=list(strategy_path),
            items=items,
        )

    def _strategy_loaders(
        self,
        source_product: RecommendationSourceProduct,
    ) -> list[
        tuple[
            RecommendationStrategy,
            Callable[[set[int], int], Awaitable[list[RecommendationCandidate]]],
        ]
    ]:
        return [
            (
                RecommendationStrategy.COOCCURRENCE,
                lambda exclude_ids, limit: self._repository.fetch_cooccurrence_candidates(
                    source_product.id,
                    exclude_ids=exclude_ids,
                    limit=limit,
                ),
            ),
            (
                RecommendationStrategy.CONTENT_BASED,
                lambda exclude_ids, limit: self._repository.fetch_content_based_candidates(
                    source_product,
                    exclude_ids=exclude_ids,
                    limit=limit,
                    category_bonus=self._config.content_category_bonus,
                    brand_bonus=self._config.content_brand_bonus,
                ),
            ),
            (
                RecommendationStrategy.POPULARITY_IN_CATEGORY,
                lambda exclude_ids, limit: self._repository.fetch_category_popularity_candidates(
                    source_product.category_id,
                    exclude_ids=exclude_ids,
                    limit=limit,
                ),
            ),
            (
                RecommendationStrategy.GLOBAL_POPULARITY,
                lambda exclude_ids, limit: self._repository.fetch_global_popularity_candidates(
                    exclude_ids=exclude_ids,
                    limit=limit,
                ),
            ),
        ]

    def _to_product(self, candidate: RecommendationCandidate) -> RecommendationProduct:
        return RecommendationProduct(
            id=candidate.id,
            sku=candidate.sku,
            title=candidate.title,
            brand=candidate.brand,
            category=candidate.category,
            price=candidate.price,
            currency=candidate.currency,
            availability=candidate.inventory_count > 0,
            rating=candidate.rating,
            popularity_score=candidate.popularity_score,
        )


def _strategy_used(strategy_path: list[RecommendationStrategy]) -> RecommendationStrategy:
    if not strategy_path:
        return RecommendationStrategy.NONE
    if len(strategy_path) == 1:
        return strategy_path[0]
    return RecommendationStrategy.FALLBACK_CHAIN


def _fallback_metric_path(strategy_path: list[RecommendationStrategy]) -> str | None:
    if not strategy_path:
        return None
    if strategy_path == [RecommendationStrategy.COOCCURRENCE]:
        return None
    return ">".join(strategy.value for strategy in strategy_path)
