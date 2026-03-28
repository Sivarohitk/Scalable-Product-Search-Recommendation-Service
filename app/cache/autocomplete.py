from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus

from redis.asyncio import Redis

from app.services.autocomplete import normalize_autocomplete_query


def build_autocomplete_cache_key(query: str, limit: int) -> str:
    normalized_query = normalize_autocomplete_query(query)
    encoded_query = quote_plus(normalized_query)
    return f"autocomplete:v1:q={encoded_query}:limit={limit}"


class RedisAutocompleteCache:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> dict[str, Any] | None:
        payload = await self._client.get(key)
        if payload is None:
            return None

        if isinstance(payload, bytes):
            raw_payload = payload.decode("utf-8")
        else:
            raw_payload = str(payload)

        data = json.loads(raw_payload)
        if not isinstance(data, Mapping):
            raise ValueError("Cached autocomplete payload must be an object")
        return dict(data)

    async def set(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
        await self._client.set(key, payload.encode("utf-8"), ex=ttl_seconds)
