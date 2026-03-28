# Scalable Product Search & Recommendation Service

Production-style ecommerce discovery backend built with FastAPI, PostgreSQL 16, `pgvector`, Redis, SQLAlchemy 2.x, Alembic, Prometheus metrics, Pytest, Ruff, Mypy, Docker Compose, and Locust.

## What is implemented
- `GET /search` with PostgreSQL full-text retrieval, trigram matching, `pgvector` semantic retrieval, hybrid ranking, debug diagnostics, and lexical fallback behavior
- `GET /autocomplete` with fast prefix matching, popularity-aware ranking, Redis caching, and cache hit/miss metrics
- `GET /recommendations/{product_id}` with deterministic co-occurrence recommendations and a staged fallback chain
- Deterministic seed generation, ingestion, and derived artifact rebuilds for local demoability
- Structured logging with `query_id` correlation
- Prometheus metrics for request volume, latency, error count, cache outcomes, and fallback usage
- Smoke tests, benchmark scripts, and a Locust mixed-traffic scenario

## What is not implemented in this repo
- No frontend beyond FastAPI docs and curl examples
- No auth layer for public or admin endpoints
- No cloud deployment, Terraform, or managed infra setup
- No external search engine such as Elasticsearch or OpenSearch
- No production embedding service or model integration; semantic retrieval uses a deterministic local embedder for demoability
- No Redis caching for `/search` or `/recommendations`; only `/autocomplete` is cached in the current version
- No production-style dashboarding or alerting layer on top of the exported Prometheus metrics

## Measured local results
These were measured on the local Docker Compose stack described in [BenchmarkReport.md](C:/Users/sivar/OneDrive/Documents/GitHub/Scalable Product Search & Recommendation Service/BenchmarkReport.md).

- `/search` benchmark: p50 `155.51 ms`, p95 `177.43 ms`
- `/autocomplete` benchmark: p50 `6.24 ms`, p95 `9.52 ms`
- `/recommendations/{product_id}` benchmark: p50 `31.90 ms`, p95 `56.65 ms`
- Locust mixed-traffic run: `626` requests in `30s`, `0` failures, aggregate throughput about `21.24 req/s`

Single-endpoint benchmark targets were met in the measured run. Under mixed Locust traffic, the heavier search query `trail-ready backpack` reached p95 about `460 ms`, so the report documents that honestly as a follow-up area.

## Architecture

### Ingestion and indexing flow
1. Generate deterministic synthetic catalog and interaction data with `scripts/generate_seed_data.py`
2. Load categories, brands, products, and interactions into PostgreSQL with `scripts/load_seed_data.py`
3. Rebuild derived artifacts with `scripts/build_artifacts.py`
4. Artifact rebuilds refresh:
   - `search_document` full-text vectors
   - product popularity rollups
   - co-view and co-purchase edges
   - deterministic product embeddings stored in `pgvector`

### Lexical retrieval
- Search starts with normalized query text
- PostgreSQL `websearch_to_tsquery` and trigram similarity fetch lexical candidates
- Ranking keeps raw lexical score metadata internally so later tuning stays modular
- Filters are applied after candidate retrieval to keep the retrieval layer simple and explainable

### Semantic retrieval
- Query embeddings are generated locally with a deterministic token-hashing embedder
- Product embeddings live in PostgreSQL in a fixed `VECTOR(16)` column
- Semantic candidates are fetched with `pgvector` cosine distance
- Weak or off-topic semantic candidates are dropped with threshold and token-overlap guards

### Hybrid ranking
`/search` combines lexical, vector, and business signals with a deterministic weighted formula:

```text
final_fused_score =
  0.55 * normalized_lexical +
  0.25 * normalized_vector +
  0.12 * normalized_popularity +
  0.05 * normalized_rating +
  0.03 * availability_boost
```

Fallback behavior:
- lexical-only if semantic retrieval is disabled
- lexical-only if vector retrieval errors
- lexical-only if vector candidates are empty or too weak

### Autocomplete caching
- `/autocomplete` is a separate prefix-oriented path, not a thin wrapper over `/search`
- Ranking uses:

```text
final_score = 0.8 * normalized_lexical + 0.2 * normalized_popularity
```

- Redis caches the final small response payload
- Cache keys are normalized and deterministic:
  `autocomplete:v1:q=<normalized_query>:limit=<limit>`
- Cache hit, miss, read-error, and write-error outcomes are exported as Prometheus metrics

### Recommendations fallback chain
`/recommendations/{product_id}` fills results stage by stage:
1. `cooccurrence`
2. `content_based`
3. `popularity_in_category`
4. `global_popularity`

The endpoint:
- excludes the source product
- deduplicates across stages
- returns `strategy_used` plus `strategy_path`
- logs stage failures explicitly and falls through instead of failing silently

### Diagnostics and monitoring
- Structured JSON request logs with `X-Request-ID` propagation
- Search debug mode exposes ranking diagnostics without changing the normal response shape
- `/metrics` exposes Prometheus counters and histograms
- Health endpoints:
  - `/health/live`
  - `/health/ready`

Prometheus metric families in the current build:
- `product_search_http_requests_total`
- `product_search_http_request_duration_seconds`
- `product_search_http_errors_total`
- `product_search_dependency_health_checks_total`
- `product_search_cache_requests_total`
- `product_search_fallbacks_total`

## Repository layout
- `app/`: API, services, repositories, cache adapters, observability
- `migrations/`: Alembic environment and revisions
- `scripts/`: seed generation, ingestion, artifact rebuild, smoke tests, benchmarks, Locust scenario
- `tests/`: API, service, and metrics tests
- `Prompt.md`, `Plan.md`, `Implement.md`, `Documentation.md`: project spec, plan, implementation rules, running log
- `BenchmarkReport.md`: measured benchmark and load-test results

## Configuration
Environment variables are prefixed with `APP_`. Important settings:

- Ports and runtime:
  - `APP_API_PORT`
  - `APP_DB_PORT`
  - `APP_REDIS_PORT`
  - `APP_LOG_LEVEL`
- Database and Redis:
  - `APP_DATABASE_URL`
  - `APP_REDIS_URL`
- Search:
  - `APP_SEARCH_SEMANTIC_ENABLED`
  - `APP_SEARCH_LEXICAL_CANDIDATE_LIMIT`
  - `APP_SEARCH_SEMANTIC_CANDIDATE_LIMIT`
  - `APP_SEARCH_VECTOR_SIMILARITY_THRESHOLD`
  - `APP_SEARCH_HYBRID_*`
- Autocomplete:
  - `APP_AUTOCOMPLETE_DEFAULT_LIMIT`
  - `APP_AUTOCOMPLETE_MAX_LIMIT`
  - `APP_AUTOCOMPLETE_CANDIDATE_LIMIT`
  - `APP_AUTOCOMPLETE_CACHE_TTL_SECONDS`
- Recommendations:
  - `APP_RECOMMENDATIONS_DEFAULT_LIMIT`
  - `APP_RECOMMENDATIONS_MAX_LIMIT`
  - `APP_RECOMMENDATIONS_CANDIDATE_LIMIT`

See [.env.example](C:/Users/sivar/OneDrive/Documents/GitHub/Scalable Product Search & Recommendation Service/.env.example) for the current defaults.

## End-to-end local demo flow

### Host Python 3.12 flow
1. Install dependencies:

```bash
python -m pip install -e .[dev]
```

2. Start PostgreSQL and Redis:

```bash
docker compose up -d db redis
```

3. Run migrations:

```bash
alembic upgrade head
```

4. Generate seed data:

```bash
python scripts/generate_seed_data.py --output-dir data/generated/default --product-count 50000 --interaction-count 250000 --seed 17
```

5. Load the seed bundle:

```bash
python scripts/load_seed_data.py --input-dir data/generated/default
```

6. Build derived artifacts:

```bash
python scripts/build_artifacts.py --embedding-batch-size 1000
```

7. Start the API:

```bash
docker compose up -d --build api
```

8. Run smoke tests:

```bash
python scripts/smoke_test.py
python scripts/smoke_test_search.py
python scripts/smoke_test_autocomplete.py
python scripts/smoke_test_recommendations.py
```

9. Run benchmarks:

```bash
python scripts/benchmark_search.py --base-url http://127.0.0.1:8000 --query northbeam --limit 5 --sort relevance --warmup 5 --iterations 25
python scripts/benchmark_autocomplete.py --base-url http://127.0.0.1:8000 --query north --limit 5 --warmup 5 --iterations 25
python scripts/benchmark_recommendations.py --base-url http://127.0.0.1:8000 --product-id 1 --limit 4 --warmup 5 --iterations 25
```

10. Run Locust:

```bash
locust -f scripts/locustfile.py --host http://127.0.0.1:8000
```

### Dockerized Python 3.12 tooling fallback
If the host does not have Python 3.12, run the tooling commands through a Python 3.12 container. This is how the final milestone was validated on the current workstation.

Example validation command:

```bash
docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && ruff check . && mypy app && pytest -q"
```

If default host ports are already in use, override them before starting the stack. Example:

```bash
APP_DB_PORT=55432 APP_API_PORT=18000 docker compose up -d --build api db redis
```

## API examples

### Search
```bash
curl "http://localhost:8000/search?query=northbeam&limit=5"
```

```bash
curl "http://localhost:8000/search?query=northbeam&limit=5&debug=true"
```

### Autocomplete
```bash
curl "http://localhost:8000/autocomplete?query=north&limit=5"
```

### Recommendations
```bash
curl "http://localhost:8000/recommendations/1?limit=4"
```

### Metrics
```bash
curl "http://localhost:8000/metrics"
```

## Smoke tests
- Base service health and metrics:
  `python scripts/smoke_test.py`
- Search:
  `python scripts/smoke_test_search.py`
- Autocomplete:
  `python scripts/smoke_test_autocomplete.py`
- Recommendations:
  `python scripts/smoke_test_recommendations.py`

## Benchmarks and load testing

### Benchmark scripts
- Search:
  `python scripts/benchmark_search.py --base-url http://127.0.0.1:8000 --query northbeam --limit 5 --sort relevance --warmup 5 --iterations 25`
- Autocomplete:
  `python scripts/benchmark_autocomplete.py --base-url http://127.0.0.1:8000 --query north --limit 5 --warmup 5 --iterations 25`
- Recommendations:
  `python scripts/benchmark_recommendations.py --base-url http://127.0.0.1:8000 --product-id 1 --limit 4 --warmup 5 --iterations 25`

Each benchmark script can also write JSON output with `--output-json`.

### Locust
The Locust scenario in [scripts/locustfile.py](C:/Users/sivar/OneDrive/Documents/GitHub/Scalable Product Search & Recommendation Service/scripts/locustfile.py) mixes search, autocomplete, and recommendation traffic with deterministic sample queries and product ids.

Headless example:

```bash
locust -f scripts/locustfile.py --host http://127.0.0.1:8000 --headless --users 10 --spawn-rate 2 --run-time 30s
```

Measured results are recorded in [BenchmarkReport.md](C:/Users/sivar/OneDrive/Documents/GitHub/Scalable Product Search & Recommendation Service/BenchmarkReport.md).

## Validation
Baseline validation commands:

```bash
docker compose config
ruff check .
mypy app
pytest -q
```

## How this maps to resume bullets
- Built a production-style FastAPI backend for ecommerce discovery using PostgreSQL, `pgvector`, Redis, SQLAlchemy, and Alembic
- Implemented hybrid product search that fuses lexical ranking, vector similarity, and business signals, with explainable debug diagnostics and explicit lexical fallback behavior
- Added Redis-backed autocomplete with normalized cache keys and Prometheus cache instrumentation, measured at p95 `9.52 ms` on the local benchmark run
- Built a deterministic recommendation pipeline with co-occurrence, content-based, category-popularity, and global-popularity fallback stages, measured at p95 `56.65 ms` on the local benchmark run
- Designed deterministic seed generation, ingestion, artifact rebuilds, smoke tests, benchmark scripts, and a Locust mixed-traffic scenario for local demoability
- Added structured logging, health checks, Prometheus metrics, and benchmark reporting for operational visibility and honest performance reporting

## Known limitations and next steps
- Search and recommendations are not cached yet. Only autocomplete uses Redis caching in the current version.
- The original project brief mentioned search-query caching, but this repo currently implements Redis caching only for autocomplete.
- The deterministic embedding model is suitable for local demoability and reproducible tests, not production semantic quality.
- The interaction graph is synthetic, so recommendation quality should not be treated as a proxy for production user behavior.
- Filters are applied after candidate retrieval in `/search`, which is simple and explainable but may need tighter candidate-window tuning at larger scale.
- Mixed Locust traffic showed heavier search and deeper recommendation fallback paths with higher p95 values than the single-endpoint benchmark runs.
- Likely next steps:
  - search-result caching and invalidation
  - recommendation caching or precomputation for hot products
  - better embedding models
  - more realistic user-behavior simulation
  - dashboarding and alerting on top of Prometheus metrics
