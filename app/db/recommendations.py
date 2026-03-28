from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import bindparam, case, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CooccurrenceType
from app.db.models import Brand, Category, Product, ProductCooccurrence
from app.services.embeddings import vector_literal
from app.services.recommendations import (
    RecommendationCandidate,
    RecommendationConfig,
    RecommendationSourceProduct,
)

CONTENT_BASED_CANDIDATES_SQL = text(
    """
SELECT
    p.id,
    p.sku,
    p.title,
    b.name AS brand,
    c.name AS category,
    p.price,
    p.currency,
    p.inventory_count,
    p.rating,
    p.popularity_score,
    (p.embedding <=> CAST(:source_embedding AS vector)) AS vector_distance,
    (
        GREATEST(
            0::double precision,
            1 - (p.embedding <=> CAST(:source_embedding AS vector))
        )
        + CASE WHEN p.category_id = :category_id THEN :category_bonus ELSE 0 END
        + CASE WHEN p.brand_id = :brand_id THEN :brand_bonus ELSE 0 END
    ) AS content_score
FROM products AS p
JOIN brands AS b ON b.id = p.brand_id
JOIN categories AS c ON c.id = p.category_id
WHERE p.id NOT IN :exclude_ids
ORDER BY content_score DESC, vector_distance ASC, p.popularity_score DESC, p.id
LIMIT :limit
"""
).bindparams(bindparam("exclude_ids", expanding=True))


class ProductRecommendationRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        config: RecommendationConfig | None = None,
    ) -> None:
        self._session = session
        self._config = config or RecommendationConfig()

    async def fetch_source_product(
        self,
        product_id: int,
    ) -> RecommendationSourceProduct | None:
        statement = select(
            Product.id,
            Product.category_id,
            Product.brand_id,
            Product.embedding,
        ).where(Product.id == product_id)
        result = await self._session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None

        return RecommendationSourceProduct(
            id=int(row.id),
            category_id=int(row.category_id),
            brand_id=int(row.brand_id),
            embedding=[float(value) for value in row.embedding],
        )

    async def fetch_cooccurrence_candidates(
        self,
        source_product_id: int,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        purchase_priority = func.max(
            case(
                (
                    ProductCooccurrence.relationship_type == CooccurrenceType.CO_PURCHASE,
                    1,
                ),
                else_=0,
            )
        ).label("purchase_priority")
        weighted_score = func.sum(
            case(
                (
                    ProductCooccurrence.relationship_type == CooccurrenceType.CO_PURCHASE,
                    ProductCooccurrence.score * self._config.co_purchase_weight,
                ),
                else_=ProductCooccurrence.score,
            )
        ).label("recommendation_score")
        total_events = func.sum(ProductCooccurrence.event_count).label("total_events")

        statement = (
            select(
                Product.id,
                Product.sku,
                Product.title,
                Brand.name.label("brand"),
                Category.name.label("category"),
                Product.price,
                Product.currency,
                Product.inventory_count,
                Product.rating,
                Product.popularity_score,
                purchase_priority,
                weighted_score,
                total_events,
            )
            .join(Product, Product.id == ProductCooccurrence.target_product_id)
            .join(Brand, Brand.id == Product.brand_id)
            .join(Category, Category.id == Product.category_id)
            .where(ProductCooccurrence.source_product_id == source_product_id)
            .where(Product.id.not_in(exclude_ids))
            .group_by(
                Product.id,
                Product.sku,
                Product.title,
                Brand.name,
                Category.name,
                Product.price,
                Product.currency,
                Product.inventory_count,
                Product.rating,
                Product.popularity_score,
            )
            .order_by(
                desc(weighted_score),
                desc(purchase_priority),
                desc(total_events),
                desc(Product.popularity_score),
                Product.id,
            )
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return [_candidate_from_row(row) for row in result]

    async def fetch_content_based_candidates(
        self,
        source_product: RecommendationSourceProduct,
        *,
        exclude_ids: set[int],
        limit: int,
        category_bonus: float,
        brand_bonus: float,
    ) -> list[RecommendationCandidate]:
        result = await self._session.execute(
            CONTENT_BASED_CANDIDATES_SQL,
            {
                "source_embedding": vector_literal(source_product.embedding),
                "category_id": source_product.category_id,
                "brand_id": source_product.brand_id,
                "category_bonus": category_bonus,
                "brand_bonus": brand_bonus,
                "exclude_ids": sorted(exclude_ids),
                "limit": limit,
            },
        )
        return [_candidate_from_row(row) for row in result.mappings()]

    async def fetch_category_popularity_candidates(
        self,
        category_id: int,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        availability_priority = case((Product.inventory_count > 0, 1), else_=0)
        statement = (
            select(
                Product.id,
                Product.sku,
                Product.title,
                Brand.name.label("brand"),
                Category.name.label("category"),
                Product.price,
                Product.currency,
                Product.inventory_count,
                Product.rating,
                Product.popularity_score,
            )
            .join(Brand, Brand.id == Product.brand_id)
            .join(Category, Category.id == Product.category_id)
            .where(Product.category_id == category_id)
            .where(Product.id.not_in(exclude_ids))
            .order_by(
                desc(availability_priority),
                desc(Product.popularity_score),
                desc(Product.rating),
                Product.id,
            )
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return [_candidate_from_row(row) for row in result]

    async def fetch_global_popularity_candidates(
        self,
        *,
        exclude_ids: set[int],
        limit: int,
    ) -> list[RecommendationCandidate]:
        availability_priority = case((Product.inventory_count > 0, 1), else_=0)
        statement = (
            select(
                Product.id,
                Product.sku,
                Product.title,
                Brand.name.label("brand"),
                Category.name.label("category"),
                Product.price,
                Product.currency,
                Product.inventory_count,
                Product.rating,
                Product.popularity_score,
            )
            .join(Brand, Brand.id == Product.brand_id)
            .join(Category, Category.id == Product.category_id)
            .where(Product.id.not_in(exclude_ids))
            .order_by(
                desc(availability_priority),
                desc(Product.popularity_score),
                desc(Product.rating),
                Product.id,
            )
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return [_candidate_from_row(row) for row in result]


def _candidate_from_row(row: object) -> RecommendationCandidate:
    row_mapping = cast(Mapping[str, Any], getattr(row, "_mapping", row))
    return RecommendationCandidate(
        id=int(row_mapping["id"]),
        sku=str(row_mapping["sku"]),
        title=str(row_mapping["title"]),
        brand=str(row_mapping["brand"]),
        category=str(row_mapping["category"]),
        price=Decimal(str(row_mapping["price"])),
        currency=str(row_mapping["currency"]),
        inventory_count=int(row_mapping["inventory_count"]),
        rating=Decimal(str(row_mapping["rating"])),
        popularity_score=Decimal(str(row_mapping["popularity_score"])),
    )
