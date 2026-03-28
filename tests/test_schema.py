from sqlalchemy import UniqueConstraint

from app.db import Base
from app.db.enums import CooccurrenceType, InteractionType


def test_schema_metadata_contains_expected_tables() -> None:
    expected_tables = {
        "categories",
        "brands",
        "products",
        "product_interactions",
        "product_cooccurrence",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_products_table_contains_catalog_and_search_columns() -> None:
    products = Base.metadata.tables["products"]

    assert {
        "id",
        "sku",
        "title",
        "description",
        "category_id",
        "brand_id",
        "price",
        "currency",
        "inventory_count",
        "rating",
        "popularity_score",
        "attributes",
        "search_document",
        "embedding",
        "created_at",
        "updated_at",
    }.issubset(products.c.keys())
    assert str(products.c.search_document.type) == "TSVECTOR"
    assert str(products.c.embedding.type) == "VECTOR(16)"
    assert any(
        isinstance(constraint, UniqueConstraint) and list(constraint.columns.keys()) == ["sku"]
        for constraint in products.constraints
    )


def test_interaction_enums_cover_expected_signal_types() -> None:
    assert {item.value for item in InteractionType} == {"view", "purchase"}
    assert {item.value for item in CooccurrenceType} == {"co_view", "co_purchase"}

