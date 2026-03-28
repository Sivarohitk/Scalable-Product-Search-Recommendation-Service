from __future__ import annotations

import os

import httpx


def main() -> None:
    base_url = os.getenv("APP_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    product_id = int(os.getenv("APP_RECOMMENDATION_PRODUCT_ID", "1"))

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        response = client.get(
            f"/recommendations/{product_id}",
            params={"limit": 4},
            headers={"X-Request-ID": "recommendations-smoke"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["query_id"] == "recommendations-smoke"
        assert payload["source_product_id"] == product_id
        assert payload["limit"] == 4
        assert payload["strategy_used"] in {
            "cooccurrence",
            "content_based",
            "popularity_in_category",
            "global_popularity",
            "fallback_chain",
        }
        assert len(payload["items"]) >= 1
        assert all(item["id"] != product_id for item in payload["items"])
        assert len(payload["strategy_path"]) >= 1

    print(
        "Smoke test passed for /recommendations fallback execution "
        f"using product_id={product_id}."
    )


if __name__ == "__main__":
    main()
