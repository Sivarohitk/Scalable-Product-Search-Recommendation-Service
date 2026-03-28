from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.autocomplete import AutocompleteExecution


class AutocompleteSuggestionResponse(BaseModel):
    id: int
    sku: str
    title: str
    brand: str
    category: str
    availability: bool


class AutocompleteResponse(BaseModel):
    query_id: str
    query: str
    normalized_query: str
    limit: int = Field(ge=1)
    items: list[AutocompleteSuggestionResponse]

    @classmethod
    def from_execution(cls, execution: AutocompleteExecution) -> AutocompleteResponse:
        return cls(
            query_id=execution.query_id,
            query=execution.query,
            normalized_query=execution.normalized_query,
            limit=execution.limit,
            items=[
                AutocompleteSuggestionResponse(
                    id=item.id,
                    sku=item.sku,
                    title=item.title,
                    brand=item.brand,
                    category=item.category,
                    availability=item.availability,
                )
                for item in execution.items
            ],
        )
