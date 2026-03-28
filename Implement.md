# Implementation Rules

## Working Rules
- Treat `Prompt.md` as the source of product requirements.
- Treat `Plan.md` as the execution sequence and complete one milestone at a time.
- Default to implementation, not speculation, unless a real ambiguity blocks progress.
- Keep changes scoped to the active milestone.
- Prefer correctness, determinism, and observability over shortcuts.
- Use explicit error handling and do not fail silently.
- Add tests and documentation updates in the same milestone as the code.

## Validation Rules
- Run validation after each milestone and fix failures before moving on.
- Baseline validation commands:
  - `ruff check .`
  - `mypy app`
  - `pytest -q`
  - `docker compose config`
- Run a local smoke test for changed endpoints or commands.

## Coding Rules
- Use Python 3.12 features where they improve clarity.
- Add type hints everywhere reasonable.
- Keep FastAPI handlers thin and push logic into services.
- Keep APIs stable, predictable, and easy to debug.
- Surface diagnostics explicitly in logs and responses when dependencies degrade.

## Milestone 1 Validation Commands
- `python -m pip install -e .[dev]`
- `ruff check .`
- `mypy app`
- `pytest -q`
- `docker compose config`
- `python scripts/smoke_test.py`

