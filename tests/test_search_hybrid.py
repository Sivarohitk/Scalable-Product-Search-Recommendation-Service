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


class FakeHybridSearchRepository:
    def __init__(
        self,
        *,
        lexical_by_query: dict[str, list[SearchCandidate]],
        vector_by_query: dict[str, list[SearchCandidate]],
        vector_error_queries: set[str] | None = None,
    ) -> None:
        self._lexical_by_query = lexical_by_query
        self._vector_by_query = vector_by_query
        self._vector_error_queries = vector_error_queries or set()
        self._current_query: str | None = None

    async def fetch_lexical_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        self._current_query = normalized_query
        return list(self._lexical_by_query.get(normalized_query, []))[:limit]

    async def fetch_vector_candidates(
        self,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        if self._current_query is None:
            raise AssertionError("Lexical candidates must be fetched before vector candidates")
        if self._current_query in self._vector_error_queries:
            raise RuntimeError("pgvector unavailable")
        return list(self._vector_by_query.get(self._current_query, []))[:limit]


def test_hybrid_ranking_combines_lexical_vector_and_business_scores() -> None:
    app = create_hybrid_app(
        lexical_by_query={"northbeam": hybrid_lexical_candidates()},
        vector_by_query={"northbeam": hybrid_vector_candidates()},
    )

    with TestClient(app) as client:
        response = client.get("/search", params={"query": "northbeam", "debug": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["debug"]["retrieval_mode"] == "hybrid"
    assert [item["id"] for item in payload["items"]] == [2, 1, 3]
    assert payload["items"][0]["debug"]["retrieval_path"] == "lexical+vector"
    assert payload["items"][0]["debug"]["final_fused_score"] > payload["items"][1]["debug"][
        "final_fused_score"
    ]


def test_hybrid_ranking_is_deterministic_for_equal_scores() -> None:
    app = create_hybrid_app(
        lexical_by_query={"tie": tied_lexical_candidates()},
        vector_by_query={"tie": tied_vector_candidates()},
    )

    with TestClient(app) as client:
        response = client.get("/search", params={"query": "tie"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [10, 11]


def test_debug_mode_returns_request_and_result_diagnostics() -> None:
    app = create_hybrid_app(
        lexical_by_query={"northbeam": hybrid_lexical_candidates()},
        vector_by_query={"northbeam": hybrid_vector_candidates()},
    )

    with TestClient(app) as client:
        response = client.get("/search", params={"query": "northbeam", "debug": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["debug"]["ranking_formula"].startswith("final_fused_score = 0.55")
    assert payload["debug"]["lexical_candidate_count"] == 3
    assert payload["debug"]["vector_candidate_count"] == 2
    assert payload["items"][0]["debug"] == {
        "lexical_score": payload["items"][0]["debug"]["lexical_score"],
        "vector_score": payload["items"][0]["debug"]["vector_score"],
        "business_boost": payload["items"][0]["debug"]["business_boost"],
        "final_fused_score": payload["items"][0]["debug"]["final_fused_score"],
        "retrieval_path": payload["items"][0]["debug"]["retrieval_path"],
        "fallback_path": None,
        "cache_used": None,
    }


def test_search_falls_back_to_lexical_when_vector_query_errors() -> None:
    app = create_hybrid_app(
        lexical_by_query={"northbeam": hybrid_lexical_candidates()},
        vector_by_query={"northbeam": hybrid_vector_candidates()},
        vector_error_queries={"northbeam"},
    )

    with TestClient(app) as client:
        response = client.get("/search", params={"query": "northbeam", "debug": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["debug"]["retrieval_mode"] == "lexical_only"
    assert payload["debug"]["fallback_path"] == "semantic_error"
    assert [item["id"] for item in payload["items"]] == [1, 2, 3]
    assert payload["items"][0]["debug"]["fallback_path"] == "semantic_error"


def test_search_falls_back_to_lexical_when_vector_scores_are_too_weak() -> None:
    app = create_hybrid_app(
        lexical_by_query={"northbeam": hybrid_lexical_candidates()},
        vector_by_query={"northbeam": weak_vector_candidates()},
    )

    with TestClient(app) as client:
        response = client.get("/search", params={"query": "northbeam", "debug": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["debug"]["retrieval_mode"] == "lexical_only"
    assert payload["debug"]["fallback_path"] == "semantic_weak"
    assert [item["id"] for item in payload["items"]] == [1, 2, 3]


def test_pagination_is_stable_under_hybrid_ranking() -> None:
    app = create_hybrid_app(
        lexical_by_query={"northbeam": hybrid_lexical_candidates()},
        vector_by_query={"northbeam": hybrid_vector_candidates()},
    )

    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={"query": "northbeam", "limit": 1, "offset": 1, "debug": "true"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 3
    assert payload["pagination"]["page"] == 2
    assert [item["id"] for item in payload["items"]] == [1]


@pytest.mark.parametrize(
    "params",
    [
        {"query": "northbeam", "debug": "maybe"},
    ],
)
def test_invalid_debug_param_returns_422(params: dict[str, str]) -> None:
    app = create_hybrid_app(
        lexical_by_query={"northbeam": hybrid_lexical_candidates()},
        vector_by_query={"northbeam": hybrid_vector_candidates()},
    )

    with TestClient(app) as client:
        response = client.get("/search", params=params)

    assert response.status_code == 422


def create_hybrid_app(
    *,
    lexical_by_query: dict[str, list[SearchCandidate]],
    vector_by_query: dict[str, list[SearchCandidate]],
    vector_error_queries: set[str] | None = None,
) -> FastAPI:
    repository = FakeHybridSearchRepository(
        lexical_by_query={
            normalize_search_query(query): list(candidates)
            for query, candidates in lexical_by_query.items()
        },
        vector_by_query={
            normalize_search_query(query): list(candidates)
            for query, candidates in vector_by_query.items()
        },
        vector_error_queries={
            normalize_search_query(query) for query in (vector_error_queries or set())
        },
    )
    config = SearchConfig(
        semantic_enabled=True,
        lexical_candidate_limit=50,
        semantic_candidate_limit=50,
        vector_similarity_threshold=0.18,
    )
    service = ProductSearchService(
        repository,
        config=config,
        embedder=lambda _: [0.0] * 16,
    )
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    return app


def hybrid_lexical_candidates() -> list[SearchCandidate]:
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
                    "rating": Decimal("4.50"),
                    "popularity_score": Decimal("7.0000"),
                    "created_at": datetime(2026, 1, 14, 12, 0, tzinfo=UTC),
                    "text_rank": 0.92,
                    "trigram_score": 0.61,
                    "lexical_score": 0.8735,
                    "vector_score": 0.0,
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
                    "inventory_count": 12,
                    "rating": Decimal("4.70"),
                    "popularity_score": Decimal("8.8000"),
                    "created_at": datetime(2026, 2, 2, 9, 30, tzinfo=UTC),
                    "text_rank": 0.71,
                    "trigram_score": 0.57,
                    "lexical_score": 0.689,
                    "vector_score": 0.0,
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
                    "rating": Decimal("4.20"),
                    "popularity_score": Decimal("6.2000"),
                    "created_at": datetime(2026, 1, 20, 8, 15, tzinfo=UTC),
                    "text_rank": 0.14,
                    "trigram_score": 0.10,
                    "lexical_score": 0.134,
                    "vector_score": 0.0,
                },
            ]
        )
    )


def hybrid_vector_candidates() -> list[SearchCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 2,
                    "sku": "ELE-NOR-000002",
                    "title": "Northbeam Compact Router for Hybrid Work",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("89.50"),
                    "inventory_count": 12,
                    "rating": Decimal("4.70"),
                    "popularity_score": Decimal("8.8000"),
                    "created_at": datetime(2026, 2, 2, 9, 30, tzinfo=UTC),
                    "text_rank": 0.0,
                    "trigram_score": 0.0,
                    "lexical_score": 0.0,
                    "vector_score": 0.91,
                    "vector_distance": 0.09,
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
                    "rating": Decimal("4.20"),
                    "popularity_score": Decimal("6.2000"),
                    "created_at": datetime(2026, 1, 20, 8, 15, tzinfo=UTC),
                    "text_rank": 0.0,
                    "trigram_score": 0.0,
                    "lexical_score": 0.0,
                    "vector_score": 0.74,
                    "vector_distance": 0.26,
                },
            ]
        )
    )


def weak_vector_candidates() -> list[SearchCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 2,
                    "sku": "ELE-NOR-000002",
                    "title": "Northbeam Compact Router for Hybrid Work",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("89.50"),
                    "inventory_count": 12,
                    "rating": Decimal("4.70"),
                    "popularity_score": Decimal("8.8000"),
                    "created_at": datetime(2026, 2, 2, 9, 30, tzinfo=UTC),
                    "text_rank": 0.0,
                    "trigram_score": 0.0,
                    "lexical_score": 0.0,
                    "vector_score": 0.10,
                    "vector_distance": 0.90,
                },
            ]
        )
    )


def tied_lexical_candidates() -> list[SearchCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 10,
                    "sku": "ELE-TIE-000010",
                    "title": "Tie Candidate Alpha",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("99.00"),
                    "inventory_count": 5,
                    "rating": Decimal("4.50"),
                    "popularity_score": Decimal("7.5000"),
                    "created_at": datetime(2026, 1, 10, 12, 0, tzinfo=UTC),
                    "text_rank": 0.80,
                    "trigram_score": 0.50,
                    "lexical_score": 0.755,
                    "vector_score": 0.0,
                },
                {
                    "id": 11,
                    "sku": "ELE-TIE-000011",
                    "title": "Tie Candidate Beta",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("99.00"),
                    "inventory_count": 5,
                    "rating": Decimal("4.50"),
                    "popularity_score": Decimal("7.5000"),
                    "created_at": datetime(2026, 1, 10, 12, 0, tzinfo=UTC),
                    "text_rank": 0.80,
                    "trigram_score": 0.50,
                    "lexical_score": 0.755,
                    "vector_score": 0.0,
                },
            ]
        )
    )


def tied_vector_candidates() -> list[SearchCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 10,
                    "sku": "ELE-TIE-000010",
                    "title": "Tie Candidate Alpha",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("99.00"),
                    "inventory_count": 5,
                    "rating": Decimal("4.50"),
                    "popularity_score": Decimal("7.5000"),
                    "created_at": datetime(2026, 1, 10, 12, 0, tzinfo=UTC),
                    "text_rank": 0.0,
                    "trigram_score": 0.0,
                    "lexical_score": 0.0,
                    "vector_score": 0.65,
                    "vector_distance": 0.35,
                },
                {
                    "id": 11,
                    "sku": "ELE-TIE-000011",
                    "title": "Tie Candidate Beta",
                    "category_slug": "electronics",
                    "category_name": "Electronics",
                    "brand_slug": "northbeam",
                    "brand_name": "Northbeam",
                    "price": Decimal("99.00"),
                    "inventory_count": 5,
                    "rating": Decimal("4.50"),
                    "popularity_score": Decimal("7.5000"),
                    "created_at": datetime(2026, 1, 10, 12, 0, tzinfo=UTC),
                    "text_rank": 0.0,
                    "trigram_score": 0.0,
                    "lexical_score": 0.0,
                    "vector_score": 0.65,
                    "vector_distance": 0.35,
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
            description=f"{definition['title']} hybrid search fixture.",
            category_slug=str(definition["category_slug"]),
            category_name=str(definition["category_name"]),
            brand_slug=str(definition["brand_slug"]),
            brand_name=str(definition["brand_name"]),
            price=Decimal(definition["price"]),
            currency="USD",
            inventory_count=int(definition["inventory_count"]),
            rating=Decimal(definition["rating"]),
            popularity_score=Decimal(definition["popularity_score"]),
            attributes={"fixture": True},
            created_at=definition["created_at"],
            updated_at=definition["created_at"],
            score_metadata=SearchScoreMetadata(
                text_rank=float(definition["text_rank"]),
                trigram_score=float(definition["trigram_score"]),
                lexical_score=float(definition["lexical_score"]),
                vector_distance=(
                    float(definition["vector_distance"])
                    if definition.get("vector_distance") is not None
                    else None
                ),
                vector_score=float(definition["vector_score"]),
            ),
        )
