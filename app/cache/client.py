import asyncio
from time import perf_counter
from typing import cast

from redis.asyncio import Redis

from app.services.health import DependencyCheckResult


class RedisProbe:
    name = "redis"

    def __init__(self, redis_url: str, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = cast(Redis, Redis.from_url(redis_url, decode_responses=False))

    @property
    def client(self) -> Redis:
        return self._client

    async def ping(self) -> DependencyCheckResult:
        started_at = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._client.ping()
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
        await self._client.aclose()
