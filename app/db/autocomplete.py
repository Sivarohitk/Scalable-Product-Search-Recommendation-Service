from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Brand, Category, Product
from app.services.autocomplete import (
    AutocompleteCandidate,
    AutocompleteScoreMetadata,
)


class ProductAutocompleteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fetch_candidates(
        self,
        normalized_query: str,
        *,
        limit: int,
    ) -> list[AutocompleteCandidate]:
        title_lower = func.lower(Product.title)
        brand_lower = func.lower(Brand.name)
        prefix_pattern = f"{normalized_query}%"
        word_prefix_pattern = f"% {normalized_query}%"

        title_prefix_match = title_lower.like(prefix_pattern)
        title_word_prefix_match = title_lower.like(word_prefix_pattern)
        brand_prefix_match = brand_lower.like(prefix_pattern)

        prefix_quality = case(
            (title_prefix_match, 1.0),
            (title_word_prefix_match, 0.88),
            (brand_prefix_match, 0.72),
            else_=0.0,
        ).label("prefix_quality")
        lexical_similarity = func.greatest(
            func.coalesce(func.similarity(title_lower, normalized_query), 0.0),
            func.coalesce(func.similarity(brand_lower, normalized_query), 0.0),
        ).label("lexical_similarity")
        lexical_score = (prefix_quality * 0.75 + lexical_similarity * 0.25).label(
            "lexical_score"
        )

        statement = (
            select(
                Product.id,
                Product.sku,
                Product.title,
                Brand.name.label("brand"),
                Category.name.label("category"),
                Product.inventory_count,
                Product.popularity_score,
                prefix_quality,
                lexical_similarity,
                lexical_score,
            )
            .join(Brand, Brand.id == Product.brand_id)
            .join(Category, Category.id == Product.category_id)
            .where(or_(title_prefix_match, title_word_prefix_match, brand_prefix_match))
            .order_by(
                desc(prefix_quality),
                desc(lexical_similarity),
                desc(Product.popularity_score),
                Product.id,
            )
            .limit(limit)
        )

        result = await self._session.execute(statement)
        return [
            AutocompleteCandidate(
                id=int(row.id),
                sku=str(row.sku),
                title=str(row.title),
                brand=str(row.brand),
                category=str(row.category),
                inventory_count=int(row.inventory_count),
                popularity_score=Decimal(str(row.popularity_score)),
                score_metadata=AutocompleteScoreMetadata(
                    prefix_quality=float(row.prefix_quality),
                    lexical_similarity=float(row.lexical_similarity),
                    lexical_score=float(row.lexical_score),
                    normalized_lexical_score=0.0,
                    normalized_popularity_score=0.0,
                    final_score=0.0,
                ),
            )
            for row in result
        ]
