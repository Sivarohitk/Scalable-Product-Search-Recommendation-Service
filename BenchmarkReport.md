# Benchmark Report

This report captures the measured local benchmark and load-test results for the final project state.

## Environment
- Host OS: Windows workstation
- Container runtime: Docker Desktop
- Tooling runtime: Dockerized Python 3.12 because the host only had Python 3.10 available
- API base URL used for the measured runs: `http://host.docker.internal:18000`
- Live dataset used for the measured runs:
  - `products=20000`
  - `product_interactions=80000`
  - `product_cooccurrence=1802`
  - `co_view_edges=1402`
  - `co_purchase_edges=400`

## Commands Used

### Stack startup
```powershell
$env:APP_DB_PORT='55432'
$env:APP_API_PORT='18000'
docker compose up -d --build api db redis
```

### Derived artifact rebuild
```bash
docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && python scripts/build_artifacts.py --database-url postgresql+asyncpg://postgres:postgres@host.docker.internal:55432/product_search --min-cooccurrence-count 2 --embedding-batch-size 1000"
```

### Smoke tests
```bash
docker run --rm -e APP_API_BASE_URL=http://host.docker.internal:18000 -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && python scripts/smoke_test.py && python scripts/smoke_test_search.py && python scripts/smoke_test_autocomplete.py && APP_RECOMMENDATION_PRODUCT_ID=1 python scripts/smoke_test_recommendations.py"
```

### Sequential endpoint benchmarks
```bash
docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && python scripts/benchmark_search.py --base-url http://host.docker.internal:18000 --query northbeam --limit 5 --sort relevance --warmup 5 --iterations 25 --output-json data/generated/benchmarks/search.json && python scripts/benchmark_autocomplete.py --base-url http://host.docker.internal:18000 --query north --limit 5 --warmup 5 --iterations 25 --output-json data/generated/benchmarks/autocomplete.json && python scripts/benchmark_recommendations.py --base-url http://host.docker.internal:18000 --product-id 1 --limit 4 --warmup 5 --iterations 25 --output-json data/generated/benchmarks/recommendations.json"
```

### Locust mixed-traffic run
```bash
docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim sh -lc "python -m pip install --upgrade pip setuptools wheel && python -m pip install -e '.[dev]' && mkdir -p data/generated/locust && locust -f scripts/locustfile.py --host http://host.docker.internal:18000 --headless --users 10 --spawn-rate 2 --run-time 30s --csv data/generated/locust/milestone8"
```

## Measured Results

### Single-endpoint benchmark scripts
These were run sequentially in one container after a warmup phase.

| Endpoint | Params | Mean | p50 | p95 | Max | Status |
|---|---|---:|---:|---:|---:|---:|
| `/search` | `query=northbeam limit=5 sort=relevance` | `160.15 ms` | `155.51 ms` | `177.43 ms` | `212.61 ms` | `200` |
| `/autocomplete` | `query=north limit=5` | `6.62 ms` | `6.24 ms` | `9.52 ms` | `10.23 ms` | `200` |
| `/recommendations/1` | `limit=4` | `36.41 ms` | `31.90 ms` | `56.65 ms` | `59.97 ms` | `200` |

### Interpretation against local demo targets
- Search target: p95 under `250 ms`
  - measured p95: `177.43 ms`
- Autocomplete target: p95 under `100 ms`
  - measured p95: `9.52 ms`
- Recommendations target: p95 under `150 ms`
  - measured p95: `56.65 ms`

All three targets were met in the measured single-endpoint benchmark run.

### Locust mixed-traffic run
Scenario:
- 10 users
- spawn rate `2/sec`
- runtime `30s`
- mixed search, autocomplete, and recommendation traffic from `scripts/locustfile.py`

Headline results:
- total requests: `626`
- failures: `0`
- aggregate throughput: about `21.24 req/s`
- aggregate median: `170 ms`
- aggregate p95: `310 ms`
- aggregate max: `510 ms`

Selected per-endpoint Locust results:

| Endpoint | Requests | Avg | p50 | p95 | Max | Failures |
|---|---:|---:|---:|---:|---:|---:|
| `/search?query=northbeam&limit=5&sort=relevance` | `95` | `216.81 ms` | `210 ms` | `310 ms` | `458 ms` | `0` |
| `/search?query=trail-ready+backpack&limit=5&sort=popularity` | `102` | `275.43 ms` | `260 ms` | `460 ms` | `510 ms` | `0` |
| `/search?query=wireless+monitor&limit=5&sort=relevance` | `116` | `237.00 ms` | `230 ms` | `340 ms` | `400 ms` | `0` |
| `/autocomplete?query=north&limit=5` | `47` | `15.00 ms` | `7 ms` | `54 ms` | `83 ms` | `0` |
| `/autocomplete?query=trail&limit=5` | `43` | `22.83 ms` | `9 ms` | `97 ms` | `150 ms` | `0` |
| `/recommendations/1?limit=4` | `26` | `79.58 ms` | `51 ms` | `210 ms` | `300 ms` | `0` |
| `/recommendations/25?limit=4` | `27` | `64.12 ms` | `54 ms` | `100 ms` | `260 ms` | `0` |
| `/recommendations/250?limit=4` | `18` | `77.09 ms` | `44 ms` | `270 ms` | `270 ms` | `0` |

## Limitations and Caveats
- These are local-demo measurements, not production capacity claims.
- `/autocomplete` benefits from Redis caching. `/search` and `/recommendations` are intentionally uncached in the current version.
- The benchmark scripts use a single representative search query and one representative recommendation product id. They are useful for repeatability, not for exhaustive relevance profiling.
- The Locust mix included heavier search queries and fallback-heavy recommendation ids. Those mixed-load p95 values were higher than the single-endpoint benchmark results.
- Recommendation quality and fallback distribution depend on the synthetic local interaction graph rather than real production behavior.
