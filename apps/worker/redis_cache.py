from __future__ import annotations

from redis.asyncio import Redis

from apps.worker.semantic_cache import CacheKey
from packages.contracts.models import Answer


class RedisSemanticCache:
    """Redis-backed answer cache with explicit TTL and JSON serialization."""

    def __init__(self, client: Redis, *, namespace: str = "axiomrag:answer") -> None:
        self._client = client
        self._namespace = namespace

    def _key(self, key: CacheKey) -> str:
        """Prefix the authorization-aware digest to avoid key collisions."""
        return f"{self._namespace}:{key.value()}"

    async def get(self, key: CacheKey) -> Answer | None:
        """Load and validate a cached answer."""
        raw = await self._client.get(self._key(key))
        if raw is None:
            return None
        return Answer.model_validate_json(raw)

    async def put(self, key: CacheKey, answer: Answer, ttl_seconds: int) -> None:
        """Store an answer with a mandatory positive TTL."""
        if ttl_seconds < 1:
            raise ValueError("cache TTL must be positive")
        await self._client.set(
            self._key(key),
            answer.model_dump_json(),
            ex=ttl_seconds,
        )
