from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.search import get_search_service
from app.main import create_app
from app.services.search import (
    ProductSearchService,
    SearchCandidate,
    SearchConfig,
    SearchScoreMetadata,
    normalize_search_query,
)


class FakeSearchRepository:
    def __init__(self, candidates_by_query: dict[str, list[SearchCandidate]]) -> None:
        self._candidates_by_query = candidates_by_query

    async def fetch_lexical_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        return list(self._candidates_by_query.get(normalized_query, []))[:limit]

    async def fetch_vector_candidates(
        self,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        return []


def test_search_happy_path_returns_typed_response_and_query_id() -> None:
    app = create_search_app({"northbeam monitor": sample_candidates()[:2]})

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={"query": "  Northbeam   Monitor  "},
            headers={"X-Request-ID": "search-happy"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "search-happy"
    payload = response.json()
    assert payload["query_id"] == "search-happy"
    assert payload["normalized_query"] == "northbeam monitor"
    assert payload["sort"] == "relevance"
    assert payload["pagination"] == {
        "total": 2,
        "limit": 20,
        "offset": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }
    assert payload["items"][0]["sku"] == "ELE-NOR-000001"
    assert payload["items"][0]["category"] == {"slug": "electronics", "name": "Electronics"}
    assert payload["items"][0]["brand"] == {"slug": "northbeam", "name": "Northbeam"}
    assert payload["items"][0]["availability"] is True


def test_search_no_results_returns_empty_collection() -> None:
    app = create_search_app({})

    with TestClient(app) as client:
        response = client.get("/search", params={"query": "no-such-product"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["pagination"]["total"] == 0
    assert payload["pagination"]["total_pages"] == 0


def test_search_filters_apply_after_candidate_fetch() -> None:
    app = create_search_app({"northbeam": sample_candidates()})

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "northbeam",
                "category": "electronics",
                "brand": "Northbeam",
                "price_min": "100.00",
                "price_max": "200.00",
                "availability": "true",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"] == {
        "category": "electronics",
        "brand": "northbeam",
        "price_min": 100.0,
        "price_max": 200.0,
        "availability": True,
    }
    assert [item["id"] for item in payload["items"]] == [1]


def test_search_sorting_supports_price_and_newest() -> None:
    app = create_search_app({"northbeam": sample_candidates()})

    with TestClient(app) as client:
        price_response = client.get(
            "/search",
            params={"query": "northbeam", "sort": "price_asc"},
        )
        newest_response = client.get(
            "/search",
            params={"query": "northbeam", "sort": "newest"},
        )

    assert price_response.status_code == 200
    assert [item["id"] for item in price_response.json()["items"]] == [2, 3, 1]

    assert newest_response.status_code == 200
    assert [item["id"] for item in newest_response.json()["items"]] == [3, 1, 2]


def test_search_pagination_supports_limit_and_offset() -> None:
    app = create_search_app({"northbeam": sample_candidates()})

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={"query": "northbeam", "limit": 1, "offset": 1},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"] == {
        "total": 3,
        "limit": 1,
        "offset": 1,
        "page": 2,
        "page_size": 1,
        "total_pages": 3,
    }
    assert [item["id"] for item in payload["items"]] == [2]


@pytest.mark.parametrize(
    ("params", "expected_fragment"),
    [
        ({"query": "   "}, "query must not be blank"),
        (
            {"query": "northbeam", "page": 1, "limit": 2},
            "use either page/page_size or limit/offset",
        ),
        (
            {"query": "northbeam", "price_min": "300", "price_max": "100"},
            "price_min must be less than or equal to price_max",
        ),
        ({"query": "northbeam", "sort": "invalid"}, "Input should be"),
    ],
)
def test_search_invalid_params_return_422(
    params: dict[str, str | int],
    expected_fragment: str,
) -> None:
    app = create_search_app({"northbeam": sample_candidates()})

    with TestClient(app) as client:
        response = client.get("/search", params=params)

    assert response.status_code == 422
    assert expected_fragment in response.text


def create_search_app(
    candidates_by_query: dict[str, list[SearchCandidate]],
) -> FastAPI:
    repository = FakeSearchRepository(
        {
            normalize_search_query(query): list(candidates)
            for query, candidates in candidates_by_query.items()
        }
    )
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: ProductSearchService(
        repository,
        config=SearchConfig(semantic_enabled=False),
    )
    return app


def sample_candidates() -> list[SearchCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 1,
                    "sku": "ELE-NOR-000001",
                    "title": "Northbeam Wireless Monitor with HDR",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("149.99"),
                    "inventory_count": 24,
                    "popularity_score": Decimal("8.7500"),
                    "created_at": datetime(2026, 1, 14, 12, 0, tzinfo=UTC),
                    "text_rank": 0.92,
                    "trigram_score": 0.61,
                    "lexical_score": 0.8735,
                },
                {
                    "id": 2,
                    "sku": "ELE-NOR-000002",
                    "title": "Northbeam Compact Router for Hybrid Work",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("89.50"),
                    "inventory_count": 0,
                    "popularity_score": Decimal("9.5000"),
                    "created_at": datetime(2025, 12, 20, 9, 30, tzinfo=UTC),
                    "text_rank": 0.71,
                    "trigram_score": 0.57,
                    "lexical_score": 0.689,
                },
                {
                    "id": 3,
                    "sku": "HOM-CIN-000003",
                    "title": "Cinderlane Adjustable Desk for Small Spaces",
                    "category_slug": "home-office",
                    "category_name": "Home Office",
                    "brand_slug": "cinderlane",
                    "brand_name": "Cinderlane",
                    "price": Decimal("109.00"),
                    "inventory_count": 14,
                    "popularity_score": Decimal("7.2000"),
                    "created_at": datetime(2026, 2, 1, 8, 15, tzinfo=UTC),
                    "text_rank": 0.68,
                    "trigram_score": 0.32,
                    "lexical_score": 0.626,
                },
            ]
        )
    )


def _build_candidates(
    definitions: Iterable[dict[str, object]],
) -> Iterable[SearchCandidate]:
    for definition in definitions:
        yield SearchCandidate(
            id=int(definition["id"]),
            sku=str(definition["sku"]),
            title=str(definition["title"]),
            description=f"{definition['title']} baseline search fixture.",
            category_slug=str(definition["category_slug"]),
            category_name=str(definition["category_name"]),
            brand_slug=str(definition["brand_slug"]),
            brand_name=str(definition["brand_name"]),
            price=Decimal(definition["price"]),
            currency="USD",
            inventory_count=int(definition["inventory_count"]),
            rating=Decimal("4.40"),
            popularity_score=Decimal(definition["popularity_score"]),
            attributes={"fixture": True},
            created_at=definition["created_at"],
            updated_at=definition["created_at"],
            score_metadata=SearchScoreMetadata(
                text_rank=float(definition["text_rank"]),
                trigram_score=float(definition["trigram_score"]),
                lexical_score=float(definition["lexical_score"]),
            ),
        )
