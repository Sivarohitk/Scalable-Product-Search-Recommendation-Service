from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    service_name: str = "product-search-service"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/product_search"
    redis_url: str = "redis://localhost:6379/0"
    health_timeout_seconds: float = 1.0
    autocomplete_default_limit: int = 8
    autocomplete_max_limit: int = 10
    autocomplete_candidate_limit: int = 40
    autocomplete_cache_ttl_seconds: int = 120
    recommendations_default_limit: int = 6
    recommendations_max_limit: int = 12
    recommendations_candidate_limit: int = 24
    search_semantic_enabled: bool = True
    search_lexical_candidate_limit: int = 250
    search_semantic_candidate_limit: int = 150
    search_vector_similarity_threshold: float = 0.18
    search_hybrid_lexical_weight: float = 0.55
    search_hybrid_vector_weight: float = 0.25
    search_hybrid_popularity_weight: float = 0.12
    search_hybrid_rating_weight: float = 0.05
    search_hybrid_availability_weight: float = 0.03

    @property
    def normalized_log_level(self) -> str:
        return self.log_level.upper()

    @property
    def database_sync_url(self) -> str:
        if "+asyncpg" in self.database_url:
            return self.database_url.replace("+asyncpg", "+psycopg", 1)

        parts = urlsplit(self.database_url)
        if parts.scheme == "postgresql":
            return urlunsplit(
                (
                    f"{parts.scheme}+psycopg",
                    parts.netloc,
                    parts.path,
                    parts.query,
                    parts.fragment,
                )
            )

        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
