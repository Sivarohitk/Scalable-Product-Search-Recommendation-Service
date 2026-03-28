from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.services.ingestion import build_derived_artifacts, load_seed_bundle
from app.services.seed import SeedConfig, generate_seed_bundle


class FakeResult:
    def __init__(
        self,
        scalar_value: int | None = None,
        mapping_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._scalar_value = scalar_value
        self._mapping_rows = mapping_rows or []

    def scalar_one(self) -> int:
        if self._scalar_value is None:
            raise AssertionError("No scalar value configured for this result")
        return self._scalar_value

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return list(self._mapping_rows)


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any | None]] = []

    def execute(self, statement: Any, params: Any | None = None) -> FakeResult:
        statement_text = str(statement)
        self.calls.append((statement_text, params))
        if "FROM products AS p" in statement_text and "category_name" in statement_text:
            return FakeResult(
                mapping_rows=[
                    {
                        "id": 1,
                        "title": "Northbeam Wireless Monitor with HDR",
                        "description": "Built for hybrid work.",
                        "attributes": {"connectivity": "usb-c"},
                        "category_name": "Electronics",
                        "brand_name": "Northbeam",
                    },
                    {
                        "id": 2,
                        "title": "Cinderlane Adjustable Desk for Small Spaces",
                        "description": "Built for home offices.",
                        "attributes": {"finish": "oak"},
                        "category_name": "Home Office",
                        "brand_name": "Cinderlane",
                    },
                ]
            )
        if "COUNT(*) FROM products WHERE search_document IS NOT NULL" in statement_text:
            return FakeResult(12)
        if "relationship_type = 'co_view'" in statement_text:
            return FakeResult(21)
        if "relationship_type = 'co_purchase'" in statement_text:
            return FakeResult(5)
        return FakeResult()


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakeConnection:
        return self._connection

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self._connection)

    def dispose(self) -> None:
        return None

def test_load_seed_bundle_inserts_expected_row_groups(tmp_path: Path, monkeypatch: Any) -> None:
    bundle_dir = tmp_path / "bundle"
    generate_seed_bundle(
        SeedConfig(
            output_dir=bundle_dir,
            product_count=12,
            interaction_count=40,
            seed=23,
        )
    )

    connection = FakeConnection()

    @contextmanager
    def _patched_sync_connection(_: str) -> Iterator[FakeEngine]:
        yield FakeEngine(connection)

    monkeypatch.setattr("app.services.ingestion.sync_connection", _patched_sync_connection)

    summary = load_seed_bundle(bundle_dir, "postgresql+asyncpg://unused", replace_existing=True)

    assert summary.categories_loaded > 0
    assert summary.brands_loaded > 0
    assert summary.products_loaded == 12
    assert summary.interactions_loaded == 40
    executed_sql = "\n".join(call[0] for call in connection.calls)
    assert (
        "TRUNCATE product_cooccurrence, product_interactions, products, brands, categories"
        in executed_sql
    )
    assert "INSERT INTO categories" in executed_sql
    assert "INSERT INTO brands" in executed_sql
    assert "INSERT INTO products" in executed_sql
    assert "INSERT INTO product_interactions" in executed_sql


def test_build_artifacts_runs_index_and_cooccurrence_sql(monkeypatch: Any) -> None:
    connection = FakeConnection()

    @contextmanager
    def _patched_sync_connection(_: str) -> Iterator[FakeEngine]:
        yield FakeEngine(connection)

    monkeypatch.setattr("app.services.ingestion.sync_connection", _patched_sync_connection)

    summary = build_derived_artifacts("postgresql+asyncpg://unused", min_cooccurrence_count=3)

    assert summary.embeddings_refreshed == 2
    assert summary.products_indexed == 12
    assert summary.co_view_edges == 21
    assert summary.co_purchase_edges == 5

    executed_sql = "\n".join(call[0] for call in connection.calls)
    assert "SET embedding = CAST(:embedding AS vector)" in executed_sql
    assert "setweight(to_tsvector" in executed_sql
    assert "TRUNCATE product_cooccurrence RESTART IDENTITY" in executed_sql
    assert "INSERT INTO product_cooccurrence" in executed_sql
