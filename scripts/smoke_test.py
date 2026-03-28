from __future__ import annotations

import os

import httpx


def main() -> None:
    base_url = os.getenv("APP_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        live_response = client.get("/health/live", headers={"X-Request-ID": "smoke-test"})
        assert live_response.status_code == 200
        assert live_response.headers["X-Request-ID"] == "smoke-test"

        readiness_response = client.get("/health/ready")
        assert readiness_response.status_code in {200, 503}
        readiness_payload = readiness_response.json()
        assert readiness_payload["status"] in {"ok", "degraded"}
        assert {item["name"] for item in readiness_payload["dependencies"]} == {
            "postgres",
            "redis",
        }

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200
        assert "product_search_http_requests_total" in metrics_response.text

    print(f"Smoke test passed for /health/live, /health/ready, and /metrics at {base_url}.")


if __name__ == "__main__":
    main()
