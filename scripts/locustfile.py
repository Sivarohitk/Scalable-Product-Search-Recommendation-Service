from __future__ import annotations

from random import choice

from locust import HttpUser, between, task

SEARCH_QUERIES = (
    {"query": "northbeam", "limit": 5, "sort": "relevance"},
    {"query": "wireless monitor", "limit": 5, "sort": "relevance"},
    {"query": "trail-ready backpack", "limit": 5, "sort": "popularity"},
)
AUTOCOMPLETE_QUERIES = (
    {"query": "north", "limit": 5},
    {"query": "wire", "limit": 5},
    {"query": "trail", "limit": 5},
    {"query": "desk", "limit": 5},
)
RECOMMENDATION_PRODUCT_IDS = (1, 6, 25, 250, 2500)


class ProductDiscoveryUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(5)
    def search(self) -> None:
        params = choice(SEARCH_QUERIES)
        with self.client.get("/search", params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"search returned {response.status_code}")

    @task(3)
    def autocomplete(self) -> None:
        params = choice(AUTOCOMPLETE_QUERIES)
        with self.client.get("/autocomplete", params=params, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"autocomplete returned {response.status_code}")

    @task(2)
    def recommendations(self) -> None:
        product_id = choice(RECOMMENDATION_PRODUCT_IDS)
        with self.client.get(
            f"/recommendations/{product_id}",
            params={"limit": 4},
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"recommendations returned {response.status_code}")
