import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.services.health import DependencyCheckResult


def make_sync_database_url(database_url: str) -> str:
    if "+asyncpg" in database_url:
        return database_url.replace("+asyncpg", "+psycopg", 1)
    return database_url


def create_sync_engine(database_url: str) -> Engine:
    return create_engine(make_sync_database_url(database_url), pool_pre_ping=True)


@contextmanager
def sync_connection(database_url: str) -> Iterator[Engine]:
    engine = create_sync_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


class DatabaseProbe:
    name = "postgres"

    def __init__(self, database_url: str, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    async def ping(self) -> DependencyCheckResult:
        started_at = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
        except Exception as exc:
            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            detail = str(exc) or exc.__class__.__name__
            return DependencyCheckResult(
                name=self.name,
                ok=False,
                detail=detail,
                latency_ms=latency_ms,
            )

        return DependencyCheckResult(
            name=self.name,
            ok=True,
            detail="ok",
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
        )

    async def close(self) -> None:
        await self._engine.dispose()
