# AGENTS.md

## Working style
- Read `Prompt.md`, `Plan.md`, `Implement.md`, and `Documentation.md` before making changes.
- Treat `Prompt.md` as the project spec and `Plan.md` as the execution plan.
- Work one milestone at a time.
- Default to action: make reasonable assumptions and implement end-to-end unless blocked by a real ambiguity.
- Keep diffs scoped and production-like.
- Prefer correctness, clarity, and observability over flashy shortcuts.

## Quality bar
- Every milestone must include code, tests, and docs updates.
- Run validation after each milestone and fix failures before moving on.
- Use type hints everywhere reasonable.
- Do not swallow errors silently.
- Keep APIs deterministic and easy to debug.

## Tech constraints
- Python 3.12
- FastAPI
- PostgreSQL as primary datastore
- `pgvector` for semantic retrieval
- Redis for caching
- SQLAlchemy 2.x + Alembic
- Docker Compose for local setup
- Pytest, Ruff, Mypy
- Prometheus metrics

## Product requirements
- Build a backend for product search, autocomplete, and recommendations.
- Implement lexical retrieval, semantic retrieval, and hybrid ranking.
- Support indexing / reindexing flows.
- Add query logging, ranking diagnostics, caching, and fallback behavior.
- Include a realistic seed-data generator so the project can be demoed locally without external dependencies.
- Include benchmark scripts and report measured latency.

## Search requirements
- Lexical retrieval: PostgreSQL full-text search and/or trigram similarity.
- Semantic retrieval: embeddings stored in `pgvector`.
- Hybrid ranking: combine lexical + vector + business boosts.
- Filters: category, brand, price range, availability.
- Sorting: relevance, price asc/desc, popularity, newest.
- Debug mode: optionally expose a score breakdown for diagnostics.

## Recommendation requirements
- Item-to-item recommendations using simulated co-view / co-purchase data.
- Content-based fallback for cold start or sparse interaction data.
- Popularity/category fallback if needed.

## Validation defaults
- `ruff check .`
- `mypy app`
- `pytest -q`
- `docker compose config`
- Run a local smoke test for changed endpoints