from __future__ import annotations

import os

import httpx


def main() -> None:
    base_url = os.getenv("APP_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        first_response = client.get(
            "/autocomplete",
            params={"query": "north", "limit": 5},
            headers={"X-Request-ID": "autocomplete-smoke"},
        )
        assert first_response.status_code == 200
        first_payload = first_response.json()
        assert first_payload["query_id"] == "autocomplete-smoke"
        assert first_payload["normalized_query"] == "north"
        assert first_payload["limit"] == 5
        assert len(first_payload["items"]) >= 1
        assert first_payload["items"][0]["title"]

        second_response = client.get(
            "/autocomplete",
            params={"query": "  NORTH ", "limit": 5},
        )
        assert second_response.status_code == 200
        second_payload = second_response.json()
        assert second_payload["normalized_query"] == "north"
        assert [item["id"] for item in second_payload["items"]] == [
            item["id"] for item in first_payload["items"]
        ]

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200
        assert 'product_search_cache_requests_total{endpoint="autocomplete",outcome="hit"}' in (
            metrics_response.text
        )
        assert 'product_search_cache_requests_total{endpoint="autocomplete",outcome="miss"}' in (
            metrics_response.text
        )

    print("Smoke test passed for /autocomplete responses, normalization, and cache metrics.")


if __name__ == "__main__":
    main()
