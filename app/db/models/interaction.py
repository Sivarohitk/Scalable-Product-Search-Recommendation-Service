from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.enums import CooccurrenceType, InteractionType


class ProductInteraction(Base):
    __tablename__ = "product_interactions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_product_interactions_product_id", "product_id"),
        Index("ix_product_interactions_session_id", "session_id"),
        Index("ix_product_interactions_user_token", "user_token"),
        Index("ix_product_interactions_order_id", "order_id"),
        Index("ix_product_interactions_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Identity(always=False), primary_key=True)
    user_token: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    interaction_type: Mapped[InteractionType] = mapped_column(
        Enum(
            InteractionType,
            name="interaction_type",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProductCooccurrence(Base):
    __tablename__ = "product_cooccurrence"
    __table_args__ = (
        CheckConstraint("event_count > 0", name="event_count_positive"),
        CheckConstraint("score >= 0", name="score_non_negative"),
        Index(
            "ix_product_cooccurrence_source_relationship",
            "source_product_id",
            "relationship_type",
        ),
        Index("ix_product_cooccurrence_target_product_id", "target_product_id"),
        Index(
            "uq_product_cooccurrence_relationship",
            "source_product_id",
            "target_product_id",
            "relationship_type",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Identity(always=False), primary_key=True)
    source_product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[CooccurrenceType] = mapped_column(
        Enum(
            CooccurrenceType,
            name="cooccurrence_type",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    source_product = relationship("Product", foreign_keys=[source_product_id])
    target_product = relationship("Product", foreign_keys=[target_product_id])
