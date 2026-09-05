from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

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


async def embed_chunks(
    provider: EmbeddingProvider,
    chunks: list[DocumentChunk],
) -> list[list[float]]:
    """Embed chunk content while preserving chunk order for point creation."""
    return await provider.embed([chunk.content for chunk in chunks])
