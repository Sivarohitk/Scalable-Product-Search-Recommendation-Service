from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.recommendations import get_recommendation_service
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.recommendations import (
    ProductRecommendationService,
    RecommendationCandidate,
    RecommendationConfig,
    RecommendationParams,
    RecommendationSourceProduct,
    RecommendationSourceProductNotFoundError,
    RecommendationStrategy,
)


class FakeRecommendationRepository:
    def __init__(
        self,
        *,
        source_products: dict[int, RecommendationSourceProduct],
        cooccurrence: dict[int, list[RecommendationCandidate]] | None = None,
        content_based: dict[int, list[RecommendationCandidate]] | None = None,
        category_popularity: dict[int, list[RecommendationCandidate]] | None = None,
        global_popularity: list[RecommendationCandidate] | None = None,
    ) -> None:
        self._source_products = source_products
        self._cooccurrence = cooccurrence or {}
        self._content_based = content_based or {}
        self._category_popularity = category_popularity or {}
        self._global_popularity = global_popularity or []

    async def fetch_source_product(
        self,
        product_id: int,
    ) -> RecommendationSourceProduct | None:
        return self._source_products.get(product_id)

    async def fetch_cooccurrence_candidates(
        self,
        source_product_id: int,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        return _filter_candidates(self._cooccurrence.get(source_product_id, []), exclude_ids, limit)

    async def fetch_content_based_candidates(
        self,
        source_product: RecommendationSourceProduct,
        *,
        exclude_ids: set[int],
        limit: int,
        category_bonus: float,
        brand_bonus: float,
    ) -> list[RecommendationCandidate]:
        return _filter_candidates(
            self._content_based.get(source_product.id, []),
            exclude_ids,
            limit,
        )

    async def fetch_category_popularity_candidates(
        self,
        category_id: int,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        return _filter_candidates(
            self._category_popularity.get(category_id, []),
            exclude_ids,
            limit,
        )

    async def fetch_global_popularity_candidates(
        self,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        return _filter_candidates(self._global_popularity, exclude_ids, limit)


def test_recommendations_happy_path_uses_cooccurrence_strategy() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product()},
            cooccurrence={1: recommendation_candidates([2, 3, 4])},
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/recommendations/1",
            params={"limit": 3},
            headers={"X-Request-ID": "recs-cooccurrence"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_id"] == "recs-cooccurrence"
    assert payload["source_product_id"] == 1
    assert payload["limit"] == 3
    assert payload["strategy_used"] == RecommendationStrategy.COOCCURRENCE.value
    assert payload["strategy_path"] == [RecommendationStrategy.COOCCURRENCE.value]
    assert [item["id"] for item in payload["items"]] == [2, 3, 4]


def test_recommendations_fall_back_from_sparse_cooccurrence_to_content() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product()},
            cooccurrence={1: recommendation_candidates([2])},
            content_based={1: recommendation_candidates([3, 4])},
        )
    )

    with TestClient(app) as client:
        response = client.get("/recommendations/1", params={"limit": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_used"] == RecommendationStrategy.FALLBACK_CHAIN.value
    assert payload["strategy_path"] == [
        RecommendationStrategy.COOCCURRENCE.value,
        RecommendationStrategy.CONTENT_BASED.value,
    ]
    assert [item["id"] for item in payload["items"]] == [2, 3, 4]


def test_recommendations_fall_back_from_content_to_category_popularity() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product(category_id=7)},
            content_based={1: recommendation_candidates([5])},
            category_popularity={7: recommendation_candidates([6, 7])},
        )
    )

    with TestClient(app) as client:
        response = client.get("/recommendations/1", params={"limit": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_path"] == [
        RecommendationStrategy.CONTENT_BASED.value,
        RecommendationStrategy.POPULARITY_IN_CATEGORY.value,
    ]
    assert [item["id"] for item in payload["items"]] == [5, 6, 7]


def test_recommendations_fall_back_to_global_popularity_when_category_is_sparse() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product(category_id=5)},
            category_popularity={5: recommendation_candidates([8])},
            global_popularity=recommendation_candidates([9, 10, 11]),
        )
    )

    with TestClient(app) as client:
        response = client.get("/recommendations/1", params={"limit": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_path"] == [
        RecommendationStrategy.POPULARITY_IN_CATEGORY.value,
        RecommendationStrategy.GLOBAL_POPULARITY.value,
    ]
    assert [item["id"] for item in payload["items"]] == [8, 9, 10]


def test_recommendations_exclude_source_product_even_if_returned_by_repository() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product()},
            cooccurrence={1: recommendation_candidates([1, 2, 3])},
            content_based={1: recommendation_candidates([1, 4])},
        )
    )

    with TestClient(app) as client:
        response = client.get("/recommendations/1", params={"limit": 3})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [2, 3, 4]


def test_recommendations_ordering_is_deterministic_for_same_stage_results() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product()},
            cooccurrence={1: recommendation_candidates([12, 13, 14])},
        )
    )

    with TestClient(app) as client:
        first_response = client.get("/recommendations/1", params={"limit": 3})
        second_response = client.get("/recommendations/1", params={"limit": 3})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["items"] == second_response.json()["items"]


def test_recommendations_invalid_product_id_returns_422() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(source_products={1: source_product()})
    )

    with TestClient(app) as client:
        response = client.get("/recommendations/0")

    assert response.status_code == 422
    assert "greater than or equal to 1" in response.text


def test_recommendations_unknown_product_returns_404() -> None:
    app = create_recommendation_app(FakeRecommendationRepository(source_products={}))

    with TestClient(app) as client:
        response = client.get("/recommendations/999999")

    assert response.status_code == 404
    assert "Product 999999 was not found" in response.text


def test_recommendations_limit_validation_and_result_limit_behavior() -> None:
    app = create_recommendation_app(
        FakeRecommendationRepository(
            source_products={1: source_product()},
            cooccurrence={1: recommendation_candidates([2, 3, 4, 5])},
        ),
        settings=Settings(
            recommendations_default_limit=3,
            recommendations_max_limit=4,
            recommendations_candidate_limit=6,
        ),
    )

    with TestClient(app) as client:
        default_response = client.get("/recommendations/1")
        limited_response = client.get("/recommendations/1", params={"limit": 2})
        invalid_response = client.get("/recommendations/1", params={"limit": 5})

    assert default_response.status_code == 200
    assert default_response.json()["limit"] == 3
    assert [item["id"] for item in default_response.json()["items"]] == [2, 3, 4]

    assert limited_response.status_code == 200
    assert limited_response.json()["limit"] == 2
    assert [item["id"] for item in limited_response.json()["items"]] == [2, 3]

    assert invalid_response.status_code == 422
    assert "limit must be less than or equal to 4" in invalid_response.text


@pytest.mark.asyncio
async def test_recommendation_service_raises_not_found_for_missing_source() -> None:
    service = ProductRecommendationService(
        FakeRecommendationRepository(source_products={}),
        config=RecommendationConfig(),
    )

    with pytest.raises(RecommendationSourceProductNotFoundError):
        await service.recommend(
            RecommendationParams(product_id=999, limit=3),
            query_id="recs-missing-source",
        )


def create_recommendation_app(
    repository: FakeRecommendationRepository,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    config = RecommendationConfig(
        default_limit=(settings.recommendations_default_limit if settings else 3),
        max_limit=(settings.recommendations_max_limit if settings else 5),
        stage_candidate_limit=(settings.recommendations_candidate_limit if settings else 8),
    )
    service = ProductRecommendationService(repository, config=config)

    app = create_app()
    app.dependency_overrides[get_recommendation_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: settings or Settings(
        recommendations_default_limit=3,
        recommendations_max_limit=5,
        recommendations_candidate_limit=8,
    )
    return app


def source_product(
    *,
    product_id: int = 1,
    category_id: int = 2,
    brand_id: int = 3,
) -> RecommendationSourceProduct:
    return RecommendationSourceProduct(
        id=product_id,
        category_id=category_id,
        brand_id=brand_id,
        embedding=[0.1] * 16,
    )


def recommendation_candidates(ids: Iterable[int]) -> list[RecommendationCandidate]:
    candidates: list[RecommendationCandidate] = []
    for product_id in ids:
        candidates.append(
            RecommendationCandidate(
                id=product_id,
                sku=f"SKU-{product_id:06d}",
                title=f"Recommended Product {product_id}",
                brand=f"Brand {product_id % 5}",
                category=f"Category {product_id % 3}",
                price=Decimal("99.99"),
                currency="USD",
                inventory_count=12 if product_id % 2 == 0 else 4,
                rating=Decimal("4.50"),
                popularity_score=Decimal(f"{10 + product_id}.0000"),
            )
        )
    return candidates


def _filter_candidates(
    candidates: Iterable[RecommendationCandidate],
    exclude_ids: set[int],
    limit: int,
) -> list[RecommendationCandidate]:
    filtered = [candidate for candidate in candidates if candidate.id not in exclude_ids]
    return filtered[:limit]
