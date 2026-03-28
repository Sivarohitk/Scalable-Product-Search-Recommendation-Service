from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Identity(always=False), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Identity(always=False), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    products: Mapped[list[Product]] = relationship(back_populates="brand")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("inventory_count >= 0", name="inventory_non_negative"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="rating_range"),
        CheckConstraint("popularity_score >= 0", name="popularity_non_negative"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_price", "price"),
        Index("ix_products_popularity_score", "popularity_score"),
        Index("ix_products_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Identity(always=False), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    inventory_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    popularity_score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    search_document: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped[Category] = relationship(back_populates="products")
    brand: Mapped[Brand] = relationship(back_populates="products")
