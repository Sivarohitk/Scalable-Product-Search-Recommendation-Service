from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import islice
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.db.enums import InteractionType
from app.db.models import Brand, Category, Product, ProductInteraction
from app.db.session import sync_connection
from app.services.embeddings import build_product_embedding, vector_literal

SEARCH_DOCUMENT_SQL = """
UPDATE products AS p
SET search_document =
    setweight(to_tsvector('english', coalesce(p.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(b.name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(c.name, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(p.description, '')), 'C')
FROM categories AS c, brands AS b
WHERE c.id = p.category_id AND b.id = p.brand_id
"""

POPULARITY_REFRESH_SQL = """
WITH interaction_activity AS (
    SELECT
        product_id,
        ln(1 + SUM(
            CASE
                WHEN interaction_type = 'purchase' THEN quantity * 6
                ELSE quantity
            END
        )) * 10 AS activity_score
    FROM product_interactions
    GROUP BY product_id
),
recalculated AS (
    SELECT
        p.id,
        ROUND(
            (p.popularity_score * 0.35 + COALESCE(a.activity_score, 0) * 0.65)::numeric,
            4
        ) AS next_score
    FROM products AS p
    LEFT JOIN interaction_activity AS a ON a.product_id = p.id
)
UPDATE products AS p
SET popularity_score = recalculated.next_score
FROM recalculated
WHERE recalculated.id = p.id
"""

CO_VIEW_SQL = """
WITH distinct_views AS (
    SELECT DISTINCT session_id, product_id
    FROM product_interactions
    WHERE interaction_type = 'view'
),
pairs AS (
    SELECT
        source.product_id AS source_product_id,
        target.product_id AS target_product_id,
        COUNT(*) AS event_count
    FROM distinct_views AS source
    JOIN distinct_views AS target
        ON source.session_id = target.session_id
        AND source.product_id <> target.product_id
    GROUP BY source.product_id, target.product_id
)
INSERT INTO product_cooccurrence (
    source_product_id,
    target_product_id,
    relationship_type,
    event_count,
    score
)
SELECT
    source_product_id,
    target_product_id,
    'co_view',
    event_count,
    ROUND((ln(1 + event_count) * 2.5)::numeric, 4)
FROM pairs
WHERE event_count >= :min_count
"""

CO_PURCHASE_SQL = """
WITH distinct_purchases AS (
    SELECT DISTINCT order_id, product_id
    FROM product_interactions
    WHERE interaction_type = 'purchase' AND order_id IS NOT NULL
),
pairs AS (
    SELECT
        source.product_id AS source_product_id,
        target.product_id AS target_product_id,
        COUNT(*) AS event_count
    FROM distinct_purchases AS source
    JOIN distinct_purchases AS target
        ON source.order_id = target.order_id
        AND source.product_id <> target.product_id
    GROUP BY source.product_id, target.product_id
)
INSERT INTO product_cooccurrence (
    source_product_id,
    target_product_id,
    relationship_type,
    event_count,
    score
)
SELECT
    source_product_id,
    target_product_id,
    'co_purchase',
    event_count,
    ROUND((ln(1 + event_count) * 3.5)::numeric, 4)
FROM pairs
WHERE event_count >= :min_count
"""

PRODUCT_EMBEDDING_SELECT_SQL = """
SELECT
    p.id,
    p.title,
    p.description,
    p.attributes,
    c.name AS category_name,
    b.name AS brand_name
FROM products AS p
JOIN categories AS c ON c.id = p.category_id
JOIN brands AS b ON b.id = p.brand_id
ORDER BY p.id
"""

PRODUCT_EMBEDDING_UPDATE_SQL = """
UPDATE products
SET embedding = CAST(:embedding AS vector)
WHERE id = :id
"""


@dataclass(frozen=True, slots=True)
class BundleSummary:
    category_count: int
    brand_count: int
    product_count: int
    interaction_count: int


@dataclass(frozen=True, slots=True)
class LoadSummary:
    categories_loaded: int
    brands_loaded: int
    products_loaded: int
    interactions_loaded: int


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    embeddings_refreshed: int
    products_indexed: int
    co_view_edges: int
    co_purchase_edges: int


def inspect_seed_bundle(bundle_dir: Path) -> BundleSummary:
    categories = _read_json(bundle_dir / "categories.json")
    brands = _read_json(bundle_dir / "brands.json")
    return BundleSummary(
        category_count=len(categories),
        brand_count=len(brands),
        product_count=_count_jsonl_records(bundle_dir / "products.jsonl"),
        interaction_count=_count_jsonl_records(bundle_dir / "interactions.jsonl"),
    )


def load_seed_bundle(
    bundle_dir: Path,
    database_url: str,
    *,
    replace_existing: bool = True,
    batch_size: int = 1_000,
) -> LoadSummary:
    manifest = _read_json(bundle_dir / "manifest.json")
    summary = inspect_seed_bundle(bundle_dir)

    if summary.product_count != int(manifest["product_count"]):
        raise ValueError("Seed bundle manifest product count does not match products.jsonl")
    if summary.interaction_count != int(manifest["interaction_count"]):
        raise ValueError("Seed bundle manifest interaction count does not match interactions.jsonl")

    categories = [_category_row(item) for item in _read_json(bundle_dir / "categories.json")]
    brands = [_brand_row(item) for item in _read_json(bundle_dir / "brands.json")]
    products_path = bundle_dir / "products.jsonl"
    interactions_path = bundle_dir / "interactions.jsonl"

    with sync_connection(database_url) as engine:
        with engine.begin() as connection:
            if replace_existing:
                connection.execute(
                    text(
                        "TRUNCATE product_cooccurrence, product_interactions, "
                        "products, brands, categories RESTART IDENTITY CASCADE"
                    )
                )

            connection.execute(insert(Category), categories)
            connection.execute(insert(Brand), brands)

            products_loaded = 0
            for batch in _batched(_iter_jsonl(products_path), batch_size):
                rows = [_product_row(item) for item in batch]
                connection.execute(insert(Product), rows)
                products_loaded += len(rows)

            interactions_loaded = 0
            for batch in _batched(_iter_jsonl(interactions_path), batch_size):
                rows = [_interaction_row(item) for item in batch]
                connection.execute(insert(ProductInteraction), rows)
                interactions_loaded += len(rows)

            _reset_sequences(connection)

    return LoadSummary(
        categories_loaded=len(categories),
        brands_loaded=len(brands),
        products_loaded=products_loaded,
        interactions_loaded=interactions_loaded,
    )


def build_derived_artifacts(
    database_url: str,
    *,
    min_cooccurrence_count: int = 2,
    embedding_batch_size: int = 1_000,
) -> ArtifactSummary:
    with sync_connection(database_url) as engine:
        with engine.begin() as connection:
            embeddings_refreshed = _refresh_product_embeddings(
                connection,
                batch_size=embedding_batch_size,
            )
            connection.execute(text(SEARCH_DOCUMENT_SQL))
            connection.execute(text(POPULARITY_REFRESH_SQL))
            connection.execute(text("TRUNCATE product_cooccurrence RESTART IDENTITY"))
            connection.execute(text(CO_VIEW_SQL), {"min_count": min_cooccurrence_count})
            connection.execute(text(CO_PURCHASE_SQL), {"min_count": min_cooccurrence_count})
            connection.execute(text("ANALYZE products"))
            connection.execute(text("ANALYZE product_interactions"))
            connection.execute(text("ANALYZE product_cooccurrence"))

            products_indexed = connection.execute(
                text("SELECT COUNT(*) FROM products WHERE search_document IS NOT NULL")
            ).scalar_one()
            co_view_edges = connection.execute(
                text(
                    "SELECT COUNT(*) FROM product_cooccurrence WHERE relationship_type = 'co_view'"
                )
            ).scalar_one()
            co_purchase_edges = connection.execute(
                text(
                    "SELECT COUNT(*) "
                    "FROM product_cooccurrence "
                    "WHERE relationship_type = 'co_purchase'"
                )
            ).scalar_one()

    return ArtifactSummary(
        embeddings_refreshed=embeddings_refreshed,
        products_indexed=int(products_indexed),
        co_view_edges=int(co_view_edges),
        co_purchase_edges=int(co_purchase_edges),
    )


def _category_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(record["id"]),
        "slug": str(record["slug"]),
        "name": str(record["name"]),
        "created_at": _parse_timestamp(record["created_at"]),
        "updated_at": _parse_timestamp(record["updated_at"]),
    }


def _brand_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(record["id"]),
        "slug": str(record["slug"]),
        "name": str(record["name"]),
        "created_at": _parse_timestamp(record["created_at"]),
        "updated_at": _parse_timestamp(record["updated_at"]),
    }


def _product_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(record["id"]),
        "sku": str(record["sku"]),
        "title": str(record["title"]),
        "description": str(record["description"]),
        "category_id": int(record["category_id"]),
        "brand_id": int(record["brand_id"]),
        "price": Decimal(str(record["price"])),
        "currency": str(record["currency"]),
        "inventory_count": int(record["inventory_count"]),
        "rating": Decimal(str(record["rating"])),
        "popularity_score": Decimal(str(record["popularity_score"])),
        "attributes": dict(record["attributes"]),
        "embedding": [float(item) for item in record["embedding"]],
        "created_at": _parse_timestamp(record["created_at"]),
        "updated_at": _parse_timestamp(record["updated_at"]),
    }


def _interaction_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_token": str(record["user_token"]),
        "session_id": str(record["session_id"]),
        "order_id": str(record["order_id"]) if record["order_id"] is not None else None,
        "product_id": int(record["product_id"]),
        "interaction_type": InteractionType(str(record["interaction_type"])),
        "quantity": int(record["quantity"]),
        "context": dict(record["context"]),
        "occurred_at": _parse_timestamp(record["occurred_at"]),
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _count_jsonl_records(path: Path) -> int:
    return sum(1 for _ in _iter_jsonl(path))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _batched(items: Iterable[dict[str, Any]], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    iterator = iter(items)
    while batch := list(islice(iterator, batch_size)):
        yield batch


def _reset_sequences(connection: Any) -> None:
    for table_name in ("categories", "brands", "products", "product_interactions"):
        connection.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), true)"
            )
        )


def _refresh_product_embeddings(connection: Any, *, batch_size: int) -> int:
    rows = connection.execute(text(PRODUCT_EMBEDDING_SELECT_SQL)).mappings().all()
    updates = [
        {
            "id": int(row["id"]),
            "embedding": vector_literal(
                build_product_embedding(
                    title=str(row["title"]),
                    description=str(row["description"]),
                    category_name=str(row["category_name"]),
                    brand_name=str(row["brand_name"]),
                    attributes=dict(row["attributes"]),
                )
            ),
        }
        for row in rows
    ]

    for batch in _batched(updates, batch_size):
        connection.execute(text(PRODUCT_EMBEDDING_UPDATE_SQL), batch)

    return len(updates)
