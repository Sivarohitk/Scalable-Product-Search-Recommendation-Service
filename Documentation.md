# Documentation Log

## Status
- Milestone 1: completed
- Milestone 2: completed
- Milestone 3 seed and ingestion scope: merged into Milestone 2 by implementation directive
- Milestone 4 lexical search baseline: completed
- Milestone 5 semantic retrieval and hybrid ranking: completed
- Milestone 6 autocomplete and cache layer: completed
- Milestone 7 recommendations and fallback chain: completed
- Milestone 8 benchmarking, load testing, and final hardening: completed

## Decisions
- The current workstation only provides Python 3.10, so validation and benchmark tooling were run through Dockerized Python 3.12 to preserve the project contract.
- PostgreSQL remains the primary store for catalog, full-text artifacts, embeddings, and recommendation signals. No external search engine was added.
- The final milestone kept code changes small and measurement-focused:
  - explicit Prometheus error counters
  - explicit Prometheus fallback counters
  - benchmark scripts for each major endpoint
  - one Locust mixed-traffic scenario
  - live-service smoke testing for `/health/*` and `/metrics`
- `product_search_http_requests_total` and `product_search_http_request_duration_seconds` remain the primary request telemetry.
- `product_search_http_errors_total` was added so error counts do not need to be inferred from request totals.
- `product_search_fallbacks_total` was added so search semantic fallbacks and recommendation fallback-chain usage are visible in Prometheus without relying only on logs.
- Search fallback usage is recorded from the existing fallback path values such as `semantic_disabled`, `semantic_error`, `semantic_empty`, and `semantic_weak`.
- Recommendation fallback usage is recorded only when the response path is not pure `cooccurrence`. Example label values include `content_based` and `cooccurrence>content_based`.
- The base smoke test was switched to target the live API over HTTP so the final milestone validates `/health/live`, `/health/ready`, and `/metrics` on the running container, not just an in-process app instance.
- Benchmark scripts were kept intentionally simple and reproducible. Each script measures one endpoint with configurable warmup and iteration counts and can optionally write JSON output.
- The final documentation distinguishes single-endpoint benchmark numbers from the mixed Locust load-test numbers. The mixed-load numbers are higher and are reported as such.

## What Implemented
- Explicit Prometheus metrics for:
  - request count
  - request latency
  - request error count
  - cache hit and miss outcomes
  - fallback usage
- Benchmark helper plus repeatable benchmark scripts for:
  - `GET /search`
  - `GET /autocomplete`
  - `GET /recommendations/{product_id}`
- A Locust scenario that exercises:
  - search traffic
  - autocomplete traffic
  - recommendation traffic
- Live-service smoke coverage for:
  - `/health/live`
  - `/health/ready`
  - `/metrics`
  - `/search`
  - `/autocomplete`
  - `/recommendations/{product_id}`
- Final README polish covering:
  - ingestion and indexing flow
  - lexical retrieval
  - semantic retrieval
  - hybrid ranking
  - autocomplete caching
  - recommendation fallback chain
  - diagnostics and monitoring
  - end-to-end local demo flow
  - benchmark and Locust commands
  - env/config overview
  - resume-bullet mapping
  - known limitations and next steps
- A tracked benchmark report in [BenchmarkReport.md](C:/Users/sivar/OneDrive/Documents/GitHub/Scalable Product Search & Recommendation Service/BenchmarkReport.md)

## Assumptions
- Local demo targets are interpreted primarily against repeatable single-endpoint benchmark runs after warmup.
- Mixed Locust traffic is useful for stress and regression visibility, but not the only source of truth for the local target check.
- Search and recommendations remain uncached by design in the current build. Mixed-load latency for those endpoints should therefore be expected to vary more than autocomplete.
- The seeded local dataset remains deterministic enough that benchmark and smoke scripts can use stable queries and product ids, including recommendation product id `1`.
- The synthetic interaction graph is good enough to exercise fallback logic and latency paths, but not good enough to claim production-grade recommendation quality.

## Run Commands
- Validation:
  `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && ruff check . && mypy app && pytest -q"`
- Stack startup on this workstation:
  `$env:APP_DB_PORT='55432'; $env:APP_API_PORT='18000'; docker compose up -d --build api db redis`
- Artifact rebuild:
  `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && python scripts/build_artifacts.py --database-url postgresql+asyncpg://postgres:postgres@host.docker.internal:55432/product_search --min-cooccurrence-count 2 --embedding-batch-size 1000"`
- Live smoke tests:
  `docker run --rm -e APP_API_BASE_URL=http://host.docker.internal:18000 -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && python scripts/smoke_test.py && python scripts/smoke_test_search.py && python scripts/smoke_test_autocomplete.py && APP_RECOMMENDATION_PRODUCT_ID=1 python scripts/smoke_test_recommendations.py"`
- Sequential benchmark run:
  `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && python scripts/benchmark_search.py --base-url http://host.docker.internal:18000 --query northbeam --limit 5 --sort relevance --warmup 5 --iterations 25 --output-json data/generated/benchmarks/search.json && python scripts/benchmark_autocomplete.py --base-url http://host.docker.internal:18000 --query north --limit 5 --warmup 5 --iterations 25 --output-json data/generated/benchmarks/autocomplete.json && python scripts/benchmark_recommendations.py --base-url http://host.docker.internal:18000 --product-id 1 --limit 4 --warmup 5 --iterations 25 --output-json data/generated/benchmarks/recommendations.json"`
- Locust run:
  `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && mkdir -p data/generated/locust && locust -f scripts/locustfile.py --host http://host.docker.internal:18000 --headless --users 10 --spawn-rate 2 --run-time 30s --csv data/generated/locust/milestone8"`
- Direct metric verification used here:
  `curl "http://localhost:18000/metrics"`

## Benchmark Notes
- Sequential single-endpoint benchmark results:
  - `/search` with `query=northbeam limit=5 sort=relevance`:
    `mean=160.15 ms p50=155.51 ms p95=177.43 ms max=212.61 ms`
  - `/autocomplete` with `query=north limit=5`:
    `mean=6.62 ms p50=6.24 ms p95=9.52 ms max=10.23 ms`
  - `/recommendations/1` with `limit=4`:
    `mean=36.41 ms p50=31.90 ms p95=56.65 ms max=59.97 ms`
- Against the stated local demo targets, the measured single-endpoint run met all three thresholds.
- Mixed-load Locust run results:
  - `626` requests over `30s`
  - `0` failures
  - aggregate throughput about `21.24 req/s`
  - aggregate p50 about `170 ms`
  - aggregate p95 about `310 ms`
- Mixed-load observations worth keeping:
  - `trail-ready backpack` search reached p95 about `460 ms`
  - `wireless monitor` search reached p95 about `340 ms`
  - recommendation ids with deeper fallback paths reached p95 between about `210 ms` and `270 ms`
- The mixed-load results do not invalidate the single-endpoint benchmark results, but they do show the current hot spots clearly.

## Known Issues
- Search and recommendations do not use Redis caching yet, so their mixed-load latency profile is more variable than autocomplete.
- The original project brief mentioned search-query caching, but the current implementation only caches autocomplete responses.
- The deterministic embedding model and deterministic interaction graph are designed for local demoability and reproducible testing, not production ranking quality.
- Filters in `/search` are still applied after candidate retrieval. This keeps the service modular and explainable, but candidate-window tuning may matter more as the dataset grows.
- Recommendation responses expose strategy metadata but not per-item score diagnostics. That is a reasonable tradeoff for the current API, but deeper debugging could still be added later.
- The measured mixed-load Locust run showed heavier search queries above the local p95 target and some recommendation ids above the target as well. Those are now documented rather than hidden.

## Follow-up Ideas
- Add search result caching with invalidation rules
- Precompute or cache hot recommendation sets
- Replace the deterministic local embedder with a higher-quality model
- Add dashboards and alert thresholds on top of the exported Prometheus metrics
- Tune candidate window sizes and ranking weights based on real traffic or offline relevance evaluation

## Validation Outcomes
- `docker compose config`: passed
- `ruff check .`: passed
- `mypy app`: passed
- `pytest -q`: passed (`52 passed`)
- `python scripts/smoke_test.py`: passed against `http://host.docker.internal:18000`
- `python scripts/smoke_test_search.py`: passed against `http://host.docker.internal:18000`
- `python scripts/smoke_test_autocomplete.py`: passed against `http://host.docker.internal:18000`
- `python scripts/smoke_test_recommendations.py`: passed against `http://host.docker.internal:18000`
- `python scripts/build_artifacts.py --database-url postgresql+asyncpg://postgres:postgres@host.docker.internal:55432/product_search --min-cooccurrence-count 2 --embedding-batch-size 1000`: passed
- `python scripts/benchmark_search.py --base-url http://host.docker.internal:18000 --query northbeam --limit 5 --sort relevance --warmup 5 --iterations 25`: passed
- `python scripts/benchmark_autocomplete.py --base-url http://host.docker.internal:18000 --query north --limit 5 --warmup 5 --iterations 25`: passed
- `python scripts/benchmark_recommendations.py --base-url http://host.docker.internal:18000 --product-id 1 --limit 4 --warmup 5 --iterations 25`: passed
- `locust -f scripts/locustfile.py --host http://host.docker.internal:18000 --headless --users 10 --spawn-rate 2 --run-time 30s --csv data/generated/locust/milestone8`: passed with `0` failures
- `/metrics` verification: passed, including `product_search_http_requests_total`, `product_search_http_request_duration_seconds`, `product_search_http_errors_total`, `product_search_cache_requests_total`, and `product_search_fallbacks_total`
