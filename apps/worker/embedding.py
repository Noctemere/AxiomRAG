from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Protocol, cast

import httpx

from packages.contracts.models import DocumentChunk


class EmbeddingProvider(Protocol):
    """Provider-neutral boundary for dense text embeddings."""

    dimension: int
    model_name: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one dense vector per input text in stable order."""
        ...


class HashEmbeddingProvider:
    """Deterministic local adapter for development and repeatable tests.

    This is not a semantic model. Replace it with a real embedding provider
    before using retrieval quality metrics or production search.
    """

    model_name = "local-hash-development"

    def __init__(self, dimension: int = 128) -> None:
        if dimension < 8:
            raise ValueError("embedding dimension must be at least 8")
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Create deterministic, L2-normalized vectors from token hashes."""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"\w+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class OpenAICompatibleEmbeddingProvider:
    """Embedding adapter for OpenAI-compatible `/embeddings` APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        dimension: int,
        batch_size: int = 64,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("embedding API key must not be empty")
        if dimension < 1:
            raise ValueError("embedding dimension must be positive")
        if batch_size < 1:
            raise ValueError("embedding batch size must be positive")
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in bounded batches and restore API-provided item order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model_name, "input": batch},
            )
            response.raise_for_status()
            vectors.extend(self._parse_response(response.json(), expected_count=len(batch)))
        return vectors

    async def aclose(self) -> None:
        """Close the HTTP client when this provider created it."""
        if self._owns_client:
            await self._client.aclose()

    def _parse_response(self, payload: Any, *, expected_count: int) -> list[list[float]]:
        raw_data: Any = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(raw_data, list) or len(cast(list[Any], raw_data)) != expected_count:
            raise ValueError("embedding response contained an unexpected item count")
        records: list[dict[str, Any]] = [
            item for item in raw_data if isinstance(item, dict)
        ]
        if len(records) != expected_count:
            raise ValueError("embedding response contained invalid items")
        ordered = sorted(records, key=lambda item: int(str(item.get("index", 0))))
        vectors: list[list[float]] = []
        for item in ordered:
            embedding: Any = item.get("embedding")
            if not isinstance(embedding, list) or len(cast(list[Any], embedding)) != self.dimension:
                raise ValueError("embedding response contained an unexpected vector dimension")
            if not all(isinstance(value, (float, int)) for value in embedding):
                raise ValueError("embedding response contained a non-numeric vector")
            vectors.append([float(value) for value in cast(list[Any], embedding)])
        return vectors


async def embed_chunks(
    provider: EmbeddingProvider,
    chunks: list[DocumentChunk],
) -> list[list[float]]:
    """Embed chunk content while preserving chunk order for point creation."""
    return await provider.embed([chunk.content for chunk in chunks])
