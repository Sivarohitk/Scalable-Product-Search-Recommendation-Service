from __future__ import annotations

import os

import httpx


def main() -> None:
    base_url = os.getenv("APP_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        search_response = client.get(
            "/search",
            params={"query": "northbeam", "limit": 3, "sort": "relevance", "debug": "true"},
            headers={"X-Request-ID": "search-smoke"},
        )
        assert search_response.status_code == 200
        search_payload = search_response.json()
        assert search_payload["query_id"] == "search-smoke"
        assert search_payload["normalized_query"] == "northbeam"
        assert search_payload["pagination"]["limit"] == 3
        assert search_payload["pagination"]["total"] >= len(search_payload["items"]) >= 1
        assert search_payload["debug"]["ranking_formula"].startswith("final_fused_score =")
        assert search_payload["items"][0]["debug"]["final_fused_score"] >= 0.0

        filtered_response = client.get(
            "/search",
            params={
                "query": "northbeam",
                "category": "electronics",
                "availability": "true",
                "sort": "price_asc",
                "limit": 2,
            },
        )
        assert filtered_response.status_code == 200
        filtered_payload = filtered_response.json()
        assert filtered_payload["filters"]["category"] == "electronics"
        assert filtered_payload["filters"]["availability"] is True
        assert filtered_payload["pagination"]["limit"] == 2

        no_result_response = client.get(
            "/search",
            params={"query": "zzznomatch", "limit": 2},
        )
        assert no_result_response.status_code == 200
        no_result_payload = no_result_response.json()
        assert no_result_payload["items"] == []
        assert no_result_payload["pagination"]["total"] == 0

    print(
        "Smoke test passed for /search hybrid retrieval, "
        "debug diagnostics, and empty-result handling."
    )


if __name__ == "__main__":
    main()
