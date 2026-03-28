# Execution Plan

## Milestone 1. Platform Bootstrap
Goal: establish the production-style service skeleton and operational baseline.

Deliverables:
- FastAPI application scaffold with typed settings and app factory
- Structured JSON logging with request correlation
- Prometheus metrics endpoint and HTTP request instrumentation
- Health endpoints with explicit dependency reporting for PostgreSQL and Redis
- Docker Compose stack for API, PostgreSQL 16 with `pgvector`, and Redis
- Tooling baseline: Ruff, Mypy, Pytest, smoke-test script, and initial README/docs

Validation:
- `ruff check .`
- `mypy app`
- `pytest -q`
- `docker compose config`
- `python scripts/smoke_test.py`

## Milestone 2. Catalog Data Model, Seed Data, and Ingestion
Goal: define the persistent catalog, generate realistic local data, and make ingestion repeatable.

Deliverables:
- SQLAlchemy models for products, categories, brands, embeddings, interactions, and query logs
- Alembic initialization and first migration
- Async database session management and repository primitives
- Deterministic seed-data generator for tens of thousands of products
- Simulated co-view and co-purchase event generation
- Seed loading and derived artifact build commands
- Tests covering schema assumptions, migration bootstrapping, seed generation, and ingestion helpers

## Milestone 3. Seed Generation and Ingestion
Goal: make the project demoable with realistic local data.

Status note:
- This scope was merged into Milestone 2 by the current implementation directive.
- The next unimplemented milestone after this pass is the lexical search baseline in Milestone 4.

Deliverables:
- Seed-data generator for tens of thousands of products
- Simulated co-view and co-purchase event generation
- Ingestion job that loads catalog and interaction data
- Reindex command skeleton for rebuilding derived artifacts
- Docs for dataset generation and loading flow

## Milestone 4. Lexical Search Baseline
Goal: deliver deterministic lexical search behavior first.

Deliverables:
- Search endpoint with PostgreSQL full-text and trigram retrieval
- Filters, sorting, and pagination
- Query normalization and structured query logging with `query_id`
- Tests and smoke coverage for baseline search behavior

## Milestone 5. Semantic Retrieval and Hybrid Ranking
Goal: add semantic relevance and explainable scoring.

Deliverables:
- Embedding-backed vector retrieval using `pgvector`
- Hybrid ranking that combines lexical, vector, and business signals
- Debug mode with score breakdown diagnostics
- Fallback to lexical-only when vector retrieval is unavailable or weak
- Tests for ranking and fallback behavior

## Milestone 6. Autocomplete and Cache Layer
Goal: optimize the fast path for short prefix queries.

Deliverables:
- Autocomplete endpoint with popularity-aware ranking
- Redis caching with normalized query keys and TTLs
- Cache hit and miss metrics
- Tests and benchmarks for autocomplete latency

## Milestone 7. Recommendations and Fallback Chain
Goal: provide resilient related-item recommendations.

Deliverables:
- Item-to-item recommendations from simulated co-occurrence data
- Content-based fallback using metadata and embeddings
- Popularity and category fallback when signals are sparse
- Tests for ranking, sparsity handling, and deterministic fallback selection

## Milestone 8. Benchmarking, Load Testing, and Final Hardening
Goal: prove local operability and performance targets.

Deliverables:
- Benchmark scripts and Locust load-test setup
- Measured latency notes and optimization follow-up items
- End-to-end Docker Compose demo flow
- Final architecture and tradeoff documentation in `README.md`
- Release-quality polish for docs, observability, and operational commands
