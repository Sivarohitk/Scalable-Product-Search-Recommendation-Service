# Scalable Product Search & Recommendation Service

## Goal
Build a production-style backend service for ecommerce product discovery using Python, FastAPI, PostgreSQL, `pgvector`, and Redis. The service must provide search, autocomplete, and recommendation APIs with low-latency local demo behavior, clean service boundaries, hybrid retrieval and ranking, ingestion and reindexing flows, structured diagnostics, caching, and fallback handling.

## Required Stack
- Python 3.12
- FastAPI
- PostgreSQL 16
- `pgvector`
- Redis
- SQLAlchemy 2.x
- Alembic
- Pytest
- Ruff
- Mypy
- Docker Compose
- Prometheus metrics
- Locust for load testing

## Functional Requirements

### 1. Search API
- Full-text lexical retrieval
- Semantic retrieval using embeddings
- Hybrid ranking that combines lexical score, vector similarity, and business boosts
- Filters: category, brand, price range, availability
- Sorting: relevance, price asc, price desc, popularity, newest
- Pagination
- Optional debug mode that returns ranking diagnostics

### 2. Autocomplete API
- Prefix and typeahead suggestions
- Popularity-aware ranking
- Fast response and cacheable behavior

### 3. Recommendations API
- Related items using item-to-item co-occurrence from simulated events
- Content-based fallback using product metadata and embeddings
- Popularity and category fallback when needed

### 4. Indexing and Ingestion
- Product catalog schema
- Seed-data generator for at least tens of thousands of products
- Ingestion job
- Reindex endpoint or command
- Derived artifacts for lexical search, vector search, and recommendation signals

### 5. Caching and Performance
- Redis caching for hot search and autocomplete queries
- Cache keys that include normalized query parameters
- Cache hit and miss metrics

### 6. Logging, Diagnostics, and Monitoring
- Structured query logging with `query_id`
- Ranking breakdown diagnostics for debug requests
- Prometheus metrics
- Health endpoint
- Basic benchmark and load-test setup

### 7. Fallback Behavior
- If vector search is unavailable or returns weak candidates, fall back to lexical-only search
- If recommendations are sparse, fall back to content-based recommendations, then popularity and category fallbacks
- Never fail silently

## Non-Goals
- No frontend beyond minimal interactive docs and curl examples
- No external cloud deployment requirement
- No external search engine such as OpenSearch or Elasticsearch in v1
- No authentication unless needed for admin endpoints in a simple way

## Desired Repository Structure
- `app/` for API, domain logic, ranking, caching, and diagnostics
- `migrations/`
- `scripts/` for seed generation, indexing, and benchmarking
- `tests/`
- `infra/` optional for local config
- `Prompt.md`
- `Plan.md`
- `Implement.md`
- `Documentation.md`
- `README.md`
- `docker-compose.yml`

## Local Performance Targets
- Search p95 under 250 ms on warm cache
- Autocomplete p95 under 100 ms on warm cache
- Recommendations p95 under 150 ms on warm cache
- All core flows must work locally with Docker Compose

## Done When
- A fresh clone starts locally with Docker Compose
- Seed data can be generated and loaded
- Search, autocomplete, and recommendation endpoints work end to end
- Hybrid ranking is implemented and explainable
- Caching, query logging, diagnostics, and fallback logic work
- Tests pass
- Benchmark scripts exist and produce results
- README explains architecture, design tradeoffs, and demo commands

