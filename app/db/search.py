from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Brand, Category, Product
from app.services.embeddings import vector_literal
from app.services.search import SearchCandidate, SearchScoreMetadata

VECTOR_CANDIDATES_SQL = """
SELECT
    p.id,
    p.sku,
    p.title,
    p.description,
    c.slug AS category_slug,
    c.name AS category_name,
    b.slug AS brand_slug,
    b.name AS brand_name,
    p.price,
    p.currency,
    p.inventory_count,
    p.rating,
    p.popularity_score,
    p.attributes,
    p.created_at,
    p.updated_at,
    (p.embedding <=> CAST(:query_embedding AS vector)) AS vector_distance,
    GREATEST(
        0::double precision,
        1 - (p.embedding <=> CAST(:query_embedding AS vector))
    ) AS vector_score
FROM products AS p
JOIN categories AS c ON c.id = p.category_id
JOIN brands AS b ON b.id = p.brand_id
ORDER BY vector_distance ASC, p.popularity_score DESC, p.id
LIMIT :limit
"""


class ProductSearchRepository:
    def __init__(self, session: AsyncSession, *, trigram_threshold: float = 0.08) -> None:
        self._session = session
        self._trigram_threshold = trigram_threshold

    async def fetch_lexical_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        ts_query = func.websearch_to_tsquery("english", normalized_query)
        text_rank = func.coalesce(func.ts_rank_cd(Product.search_document, ts_query), 0.0).label(
            "text_rank"
        )
        trigram_score = func.coalesce(func.similarity(Product.title, normalized_query), 0.0).label(
            "trigram_score"
        )
        lexical_score = (text_rank * 0.85 + trigram_score * 0.15).label("lexical_score")
        text_match = Product.search_document.op("@@")(ts_query)

        statement = (
            select(
                Product.id,
                Product.sku,
                Product.title,
                Product.description,
                Category.slug.label("category_slug"),
                Category.name.label("category_name"),
                Brand.slug.label("brand_slug"),
                Brand.name.label("brand_name"),
                Product.price,
                Product.currency,
                Product.inventory_count,
                Product.rating,
                Product.popularity_score,
                Product.attributes,
                Product.created_at,
                Product.updated_at,
                text_rank,
                trigram_score,
                lexical_score,
            )
            .join(Category, Category.id == Product.category_id)
            .join(Brand, Brand.id == Product.brand_id)
            .where(or_(text_match, trigram_score >= self._trigram_threshold))
            .order_by(
                desc(lexical_score),
                desc(Product.popularity_score),
                Product.id,
            )
            .limit(limit)
        )

        result = await self._session.execute(statement)
        return [_candidate_from_row(row) for row in result]

    async def fetch_vector_candidates(
        self,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[SearchCandidate]:
        result = await self._session.execute(
            text(VECTOR_CANDIDATES_SQL),
            {"query_embedding": vector_literal(query_embedding), "limit": limit},
        )
        return [_candidate_from_row(row) for row in result.mappings()]


def _candidate_from_row(row: object) -> SearchCandidate:
    row_mapping = cast(Mapping[str, Any], getattr(row, "_mapping", row))
    return SearchCandidate(
        id=int(row_mapping["id"]),
        sku=str(row_mapping["sku"]),
        title=str(row_mapping["title"]),
        description=str(row_mapping["description"]),
        category_slug=str(row_mapping["category_slug"]),
        category_name=str(row_mapping["category_name"]),
        brand_slug=str(row_mapping["brand_slug"]),
        brand_name=str(row_mapping["brand_name"]),
        price=Decimal(str(row_mapping["price"])),
        currency=str(row_mapping["currency"]),
        inventory_count=int(row_mapping["inventory_count"]),
        rating=Decimal(str(row_mapping["rating"])),
        popularity_score=Decimal(str(row_mapping["popularity_score"])),
        attributes=dict(row_mapping["attributes"]),
        created_at=row_mapping["created_at"],
        updated_at=row_mapping["updated_at"],
        score_metadata=SearchScoreMetadata(
            text_rank=float(row_mapping.get("text_rank") or 0.0),
            trigram_score=float(row_mapping.get("trigram_score") or 0.0),
            lexical_score=float(row_mapping.get("lexical_score") or 0.0),
            vector_distance=(
                float(row_mapping["vector_distance"])
                if row_mapping.get("vector_distance") is not None
                else None
            ),
            vector_score=float(row_mapping.get("vector_score") or 0.0),
        ),
    )
