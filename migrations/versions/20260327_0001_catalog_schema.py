"""Create catalog, interaction, and artifact tables."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "20260327_0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamp_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _jsonb_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    interaction_type = postgresql.ENUM(
        "view",
        "purchase",
        name="interaction_type",
        create_type=False,
    )
    cooccurrence_type = postgresql.ENUM(
        "co_view",
        "co_purchase",
        name="cooccurrence_type",
        create_type=False,
    )
    interaction_type.create(op.get_bind(), checkfirst=True)
    cooccurrence_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        _timestamp_column("created_at"),
        _timestamp_column("updated_at"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )

    op.create_table(
        "brands",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        _timestamp_column("created_at"),
        _timestamp_column("updated_at"),
        sa.UniqueConstraint("slug", name="uq_brands_slug"),
        sa.UniqueConstraint("name", name="uq_brands_name"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=4000), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("brand_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("inventory_count", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Numeric(3, 2), nullable=False),
        sa.Column("popularity_score", sa.Numeric(10, 4), nullable=False),
        _jsonb_column("attributes"),
        sa.Column("search_document", postgresql.TSVECTOR(), nullable=True),
        sa.Column("embedding", Vector(16), nullable=False),
        _timestamp_column("created_at"),
        _timestamp_column("updated_at"),
        sa.CheckConstraint(
            "inventory_count >= 0",
            name="inventory_non_negative",
        ),
        sa.CheckConstraint(
            "popularity_score >= 0",
            name="popularity_non_negative",
        ),
        sa.CheckConstraint("price >= 0", name="price_non_negative"),
        sa.CheckConstraint("rating >= 0 AND rating <= 5", name="rating_range"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_price", "products", ["price"])
    op.create_index("ix_products_popularity_score", "products", ["popularity_score"])
    op.create_index("ix_products_created_at", "products", ["created_at"])
    op.create_index(
        "ix_products_search_document",
        "products",
        ["search_document"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_products_title_trgm",
        "products",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    op.create_table(
        "product_interactions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("user_token", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("interaction_type", interaction_type, nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        _jsonb_column("context"),
        _timestamp_column("occurred_at"),
        sa.CheckConstraint(
            "quantity > 0",
            name="quantity_positive",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_product_interactions_product_id", "product_interactions", ["product_id"])
    op.create_index("ix_product_interactions_session_id", "product_interactions", ["session_id"])
    op.create_index("ix_product_interactions_user_token", "product_interactions", ["user_token"])
    op.create_index("ix_product_interactions_order_id", "product_interactions", ["order_id"])
    op.create_index("ix_product_interactions_occurred_at", "product_interactions", ["occurred_at"])

    op.create_table(
        "product_cooccurrence",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("source_product_id", sa.BigInteger(), nullable=False),
        sa.Column("target_product_id", sa.BigInteger(), nullable=False),
        sa.Column("relationship_type", cooccurrence_type, nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(12, 4), nullable=False),
        _timestamp_column("updated_at"),
        sa.CheckConstraint(
            "event_count > 0",
            name="event_count_positive",
        ),
        sa.CheckConstraint(
            "score >= 0",
            name="score_non_negative",
        ),
        sa.ForeignKeyConstraint(["source_product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_product_id"], ["products.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_product_cooccurrence_source_relationship",
        "product_cooccurrence",
        ["source_product_id", "relationship_type"],
    )
    op.create_index(
        "ix_product_cooccurrence_target_product_id",
        "product_cooccurrence",
        ["target_product_id"],
    )
    op.create_index(
        "uq_product_cooccurrence_relationship",
        "product_cooccurrence",
        ["source_product_id", "target_product_id", "relationship_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_product_cooccurrence_relationship", table_name="product_cooccurrence")
    op.drop_index("ix_product_cooccurrence_target_product_id", table_name="product_cooccurrence")
    op.drop_index("ix_product_cooccurrence_source_relationship", table_name="product_cooccurrence")
    op.drop_table("product_cooccurrence")

    op.drop_index("ix_product_interactions_occurred_at", table_name="product_interactions")
    op.drop_index("ix_product_interactions_order_id", table_name="product_interactions")
    op.drop_index("ix_product_interactions_user_token", table_name="product_interactions")
    op.drop_index("ix_product_interactions_session_id", table_name="product_interactions")
    op.drop_index("ix_product_interactions_product_id", table_name="product_interactions")
    op.drop_table("product_interactions")

    op.drop_index("ix_products_title_trgm", table_name="products")
    op.drop_index("ix_products_search_document", table_name="products")
    op.drop_index("ix_products_created_at", table_name="products")
    op.drop_index("ix_products_popularity_score", table_name="products")
    op.drop_index("ix_products_price", table_name="products")
    op.drop_index("ix_products_brand_id", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")

    op.drop_table("brands")
    op.drop_table("categories")

    cooccurrence_type = sa.Enum(name="cooccurrence_type")
    interaction_type = sa.Enum(name="interaction_type")
    cooccurrence_type.drop(op.get_bind(), checkfirst=True)
    interaction_type.drop(op.get_bind(), checkfirst=True)
