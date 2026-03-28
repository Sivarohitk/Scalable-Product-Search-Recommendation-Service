from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.recommendations import RecommendationExecution, RecommendationStrategy


class RecommendationProductResponse(BaseModel):
    id: int
    sku: str
    title: str
    brand: str
    category: str
    price: float
    currency: str
    availability: bool
    rating: float
    popularity_score: float


class RecommendationsResponse(BaseModel):
    query_id: str
    source_product_id: int
    limit: int = Field(ge=1)
    strategy_used: RecommendationStrategy
    strategy_path: list[RecommendationStrategy]
    items: list[RecommendationProductResponse]

    @classmethod
    def from_execution(cls, execution: RecommendationExecution) -> RecommendationsResponse:
        return cls(
            query_id=execution.query_id,
            source_product_id=execution.source_product_id,
            limit=execution.limit,
            strategy_used=execution.strategy_used,
            strategy_path=execution.strategy_path,
            items=[
                RecommendationProductResponse(
                    id=item.id,
                    sku=item.sku,
                    title=item.title,
                    brand=item.brand,
                    category=item.category,
                    price=float(item.price),
                    currency=item.currency,
                    availability=item.availability,
                    rating=float(item.rating),
                    popularity_score=float(item.popularity_score),
                )
                for item in execution.items
            ],
        )
