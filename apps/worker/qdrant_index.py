from __future__ import annotations

from typing import Protocol
from uuid import UUID

from packages.contracts.models import DocumentChunk


class VectorIndex(Protocol):
    """Minimal vector-index boundary used by worker orchestration."""

    async def ensure_collection(self, *, dimension: int) -> None:
        """Create or validate the dense-vector collection."""
        ...

    async def upsert_chunks(
        self,
        *,
        tenant_id: UUID,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        model_name: str,
    ) -> int:
        """Upsert vectors and provenance payloads, returning the point count."""
        ...


class QdrantVectorIndex:
    """Qdrant adapter for dense vectors and provenance-filterable payloads."""

    def __init__(self, client: object, collection_name: str) -> None:
        self._client = client
        self._collection_name = collection_name

    async def ensure_collection(self, *, dimension: int) -> None:
        """Create the collection when absent and keep cosine distance explicit."""
        from qdrant_client.http import models

        exists = await self._client.collection_exists(collection_name=self._collection_name)  # type: ignore[attr-defined]
        if not exists:
            await self._client.create_collection(  # type: ignore[attr-defined]
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    async def upsert_chunks(
        self,
        *,
        tenant_id: UUID,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        model_name: str,
    ) -> int:
        """Write vectors with tenant and citation metadata as payload."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal lengths")
        from qdrant_client.http import models

        points = [
            models.PointStruct(
                id=str(chunk.chunk_id),
                vector=vector,
                payload={
                    "tenant_id": str(tenant_id),
                    "document_id": str(chunk.document_id),
                    "chunk_id": str(chunk.chunk_id),
                    "content": chunk.content,
                    "modality": chunk.modality.value,
                    "page_number": chunk.provenance.page_number,
                    "region_id": chunk.provenance.region_id,
                    "embedding_model": model_name,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if points:
            await self._client.upsert(  # type: ignore[attr-defined]
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
        return len(points)
