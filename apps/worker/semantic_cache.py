from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from packages.contracts.models import Answer, RetrievalFilter


@dataclass(frozen=True)
class CacheKey:
    """Authorization- and retrieval-aware semantic cache identity."""

    tenant_id: UUID
    query: str
    filters: RetrievalFilter | None
    embedding_model: str
    index_version: str

    def value(self) -> str:
        """Return a stable digest that prevents cross-tenant cache leakage."""
        payload = {
            "tenant_id": str(self.tenant_id),
            "query": self.query.strip().lower(),
            "filters": self.filters.model_dump(mode="json") if self.filters else None,
            "embedding_model": self.embedding_model,
            "index_version": self.index_version,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class SemanticCache(Protocol):
    """Cache boundary for answer reuse."""

    async def get(self, key: CacheKey) -> Answer | None:
        """Return a cached answer or None."""
        ...

    async def put(self, key: CacheKey, answer: Answer, ttl_seconds: int) -> None:
        """Store an answer for a bounded lifetime."""
        ...


class InMemorySemanticCache:
    """Deterministic cache for local development and tests."""

    def __init__(self) -> None:
        self._values: dict[str, Answer] = {}

    async def get(self, key: CacheKey) -> Answer | None:
        """Return the answer stored for the exact authorization-aware key."""
        return self._values.get(key.value())

    async def put(self, key: CacheKey, answer: Answer, ttl_seconds: int) -> None:
        """Store an answer and reject invalid TTL configuration."""
        if ttl_seconds < 1:
            raise ValueError("cache TTL must be positive")
        self._values[key.value()] = answer
