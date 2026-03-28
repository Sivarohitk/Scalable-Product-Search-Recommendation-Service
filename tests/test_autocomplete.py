from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.autocomplete import get_autocomplete_service
from app.cache.autocomplete import build_autocomplete_cache_key
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.autocomplete import (
    AutocompleteCandidate,
    AutocompleteConfig,
    AutocompleteParams,
    AutocompleteScoreMetadata,
    ProductAutocompleteService,
)


class FakeAutocompleteRepository:
    def __init__(self, candidates_by_query: dict[str, list[AutocompleteCandidate]]) -> None:
        self._candidates_by_query = candidates_by_query
        self.calls: list[tuple[str, int]] = []

    async def fetch_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[AutocompleteCandidate]:
        self.calls.append((normalized_query, limit))
        return list(self._candidates_by_query.get(normalized_query, []))[:limit]


class FakeAutocompleteCache:
    def __init__(
        self,
        *,
        initial: dict[str, dict[str, object]] | None = None,
        fail_get: bool = False,
        fail_set: bool = False,
    ) -> None:
        self.values = deepcopy(initial or {})
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, int]] = []

    async def get(self, key: str) -> dict[str, object] | None:
        self.get_calls.append(key)
        if self.fail_get:
            raise RuntimeError("redis unavailable")
        value = self.values.get(key)
        return deepcopy(value) if value is not None else None

    async def set(self, key: str, value: dict[str, object], *, ttl_seconds: int) -> None:
        self.set_calls.append((key, ttl_seconds))
        if self.fail_set:
            raise RuntimeError("redis unavailable")
        self.values[key] = deepcopy(value)


def test_autocomplete_prefix_matching_happy_path() -> None:
    repository = FakeAutocompleteRepository({"north": sample_candidates()})
    service = create_autocomplete_service(repository)
    app = create_autocomplete_app(service)

    with TestClient(app) as client:
        response = client.get(
            "/autocomplete",
            params={"query": "  North  "},
            headers={"X-Request-ID": "autocomplete-happy"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_id"] == "autocomplete-happy"
    assert payload["normalized_query"] == "north"
    assert payload["limit"] == 5
    assert [item["id"] for item in payload["items"]] == [1, 2, 3]
    assert payload["items"][0]["title"].startswith("Northbeam")


def test_autocomplete_popularity_boost_affects_ordering() -> None:
    repository = FakeAutocompleteRepository({"north": popularity_tied_candidates()})
    service = create_autocomplete_service(repository)
    app = create_autocomplete_app(service)

    with TestClient(app) as client:
        response = client.get("/autocomplete", params={"query": "north"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [11, 10]


def test_autocomplete_empty_query_returns_422() -> None:
    repository = FakeAutocompleteRepository({})
    service = create_autocomplete_service(repository)
    app = create_autocomplete_app(service)

    with TestClient(app) as client:
        response = client.get("/autocomplete", params={"query": "   "})

    assert response.status_code == 422
    assert "query must not be blank" in response.text


@pytest.mark.parametrize(
    ("params", "expected_fragment"),
    [
        ({"query": "north", "limit": "0"}, "greater than or equal to 1"),
        ({"query": "north", "limit": "9"}, "limit must be less than or equal to 8"),
        ({"query": "north", "limit": "bad"}, "valid integer"),
    ],
)
def test_autocomplete_invalid_params_return_422(
    params: dict[str, str],
    expected_fragment: str,
) -> None:
    repository = FakeAutocompleteRepository({})
    service = create_autocomplete_service(repository)
    app = create_autocomplete_app(service)

    with TestClient(app) as client:
        response = client.get("/autocomplete", params=params)

    assert response.status_code == 422
    assert expected_fragment in response.text


def test_autocomplete_respects_requested_limit() -> None:
    repository = FakeAutocompleteRepository({"north": sample_candidates()})
    service = create_autocomplete_service(repository)
    app = create_autocomplete_app(service)

    with TestClient(app) as client:
        response = client.get("/autocomplete", params={"query": "north", "limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 2
    assert [item["id"] for item in payload["items"]] == [1, 2]


def test_autocomplete_deterministic_ordering_breaks_ties_by_id() -> None:
    repository = FakeAutocompleteRepository({"north": tied_candidates()})
    service = create_autocomplete_service(repository)
    app = create_autocomplete_app(service)

    with TestClient(app) as client:
        response = client.get("/autocomplete", params={"query": "north"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [20, 21]


def test_autocomplete_cache_key_normalizes_query() -> None:
    assert build_autocomplete_cache_key("  North   Beam ", 5) == build_autocomplete_cache_key(
        "north beam",
        5,
    )


@pytest.mark.asyncio
async def test_autocomplete_cache_miss_populates_cache() -> None:
    repository = FakeAutocompleteRepository({"north": sample_candidates()})
    cache = FakeAutocompleteCache()
    service = create_autocomplete_service(repository, cache=cache)

    result = await service.autocomplete(
        AutocompleteParams(query="north", limit=2),
        query_id="autocomplete-cache-miss",
    )

    assert [item.id for item in result.items] == [1, 2]
    assert repository.calls == [("north", 20)]
    assert cache.get_calls == [build_autocomplete_cache_key("north", 2)]
    assert cache.set_calls == [(build_autocomplete_cache_key("north", 2), 60)]


@pytest.mark.asyncio
async def test_autocomplete_cache_hit_avoids_repository_round_trip() -> None:
    repository = FakeAutocompleteRepository({"north": sample_candidates()})
    cache = FakeAutocompleteCache()
    service = create_autocomplete_service(repository, cache=cache)

    first_result = await service.autocomplete(
        AutocompleteParams(query="north", limit=2),
        query_id="autocomplete-first",
    )
    second_result = await service.autocomplete(
        AutocompleteParams(query=" NORTH ", limit=2),
        query_id="autocomplete-second",
    )

    assert [item.id for item in first_result.items] == [1, 2]
    assert [item.id for item in second_result.items] == [1, 2]
    assert repository.calls == [("north", 20)]
    assert cache.get_calls == [
        build_autocomplete_cache_key("north", 2),
        build_autocomplete_cache_key("north", 2),
    ]
    assert len(cache.set_calls) == 1


@pytest.mark.asyncio
async def test_autocomplete_falls_back_when_cache_read_fails() -> None:
    repository = FakeAutocompleteRepository({"north": sample_candidates()})
    cache = FakeAutocompleteCache(fail_get=True)
    service = create_autocomplete_service(repository, cache=cache)

    result = await service.autocomplete(
        AutocompleteParams(query="north", limit=2),
        query_id="autocomplete-cache-error",
    )

    assert [item.id for item in result.items] == [1, 2]
    assert repository.calls == [("north", 20)]


def create_autocomplete_app(service: ProductAutocompleteService) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_autocomplete_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(
        autocomplete_default_limit=5,
        autocomplete_max_limit=8,
        autocomplete_candidate_limit=20,
        autocomplete_cache_ttl_seconds=60,
    )
    return app


def create_autocomplete_service(
    repository: FakeAutocompleteRepository,
    *,
    cache: FakeAutocompleteCache | None = None,
) -> ProductAutocompleteService:
    config = AutocompleteConfig(
        default_limit=5,
        max_limit=8,
        candidate_limit=20,
        cache_ttl_seconds=60,
    )
    return ProductAutocompleteService(repository, cache=cache, config=config)


def sample_candidates() -> list[AutocompleteCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 1,
                    "sku": "ELE-NOR-000001",
                    "title": "Northbeam Wireless Monitor with HDR",
                    "brand": "Northbeam",
                    "category": "Electronics",
                    "inventory_count": 24,
                    "popularity_score": Decimal("8.8000"),
                    "prefix_quality": 1.0,
                    "lexical_similarity": 0.92,
                    "lexical_score": 0.98,
                },
                {
                    "id": 2,
                    "sku": "ELE-NOR-000002",
                    "title": "Northbeam Compact Router for Hybrid Work",
                    "brand": "Northbeam",
                    "category": "Electronics",
                    "inventory_count": 12,
                    "popularity_score": Decimal("8.1000"),
                    "prefix_quality": 1.0,
                    "lexical_similarity": 0.83,
                    "lexical_score": 0.94,
                },
                {
                    "id": 3,
                    "sku": "OFF-NOR-000003",
                    "title": "Hybrid North Desk Lamp",
                    "brand": "Northbeam",
                    "category": "Office",
                    "inventory_count": 0,
                    "popularity_score": Decimal("7.5000"),
                    "prefix_quality": 0.88,
                    "lexical_similarity": 0.74,
                    "lexical_score": 0.845,
                },
            ]
        )
    )


def popularity_tied_candidates() -> list[AutocompleteCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 10,
                    "sku": "ELE-NOR-000010",
                    "title": "Northbeam Audio Dock",
                    "brand": "Northbeam",
                    "category": "Electronics",
                    "inventory_count": 8,
                    "popularity_score": Decimal("4.0000"),
                    "prefix_quality": 1.0,
                    "lexical_similarity": 0.85,
                    "lexical_score": 0.95,
                },
                {
                    "id": 11,
                    "sku": "ELE-NOR-000011",
                    "title": "Northbeam Audio Dock Pro",
                    "brand": "Northbeam",
                    "category": "Electronics",
                    "inventory_count": 8,
                    "popularity_score": Decimal("9.0000"),
                    "prefix_quality": 1.0,
                    "lexical_similarity": 0.85,
                    "lexical_score": 0.95,
                },
            ]
        )
    )


def tied_candidates() -> list[AutocompleteCandidate]:
    return list(
        _build_candidates(
            [
                {
                    "id": 20,
                    "sku": "ELE-NOR-000020",
                    "title": "Northbeam Tie Alpha",
                    "brand": "Northbeam",
                    "category": "Electronics",
                    "inventory_count": 5,
                    "popularity_score": Decimal("7.0000"),
                    "prefix_quality": 1.0,
                    "lexical_similarity": 0.81,
                    "lexical_score": 0.92,
                },
                {
                    "id": 21,
                    "sku": "ELE-NOR-000021",
                    "title": "Northbeam Tie Beta",
                    "brand": "Northbeam",
                    "category": "Electronics",
                    "inventory_count": 5,
                    "popularity_score": Decimal("7.0000"),
                    "prefix_quality": 1.0,
                    "lexical_similarity": 0.81,
                    "lexical_score": 0.92,
                },
            ]
        )
    )


def _build_candidates(
    definitions: Iterable[dict[str, object]],
) -> Iterable[AutocompleteCandidate]:
    for definition in definitions:
        yield AutocompleteCandidate(
            id=int(definition["id"]),
            sku=str(definition["sku"]),
            title=str(definition["title"]),
            brand=str(definition["brand"]),
            category=str(definition["category"]),
            inventory_count=int(definition["inventory_count"]),
            popularity_score=Decimal(definition["popularity_score"]),
            score_metadata=AutocompleteScoreMetadata(
                prefix_quality=float(definition["prefix_quality"]),
                lexical_similarity=float(definition["lexical_similarity"]),
                lexical_score=float(definition["lexical_score"]),
                normalized_lexical_score=0.0,
                normalized_popularity_score=0.0,
                final_score=0.0,
            ),
        )
