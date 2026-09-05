from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from packages.contracts.models import (
    DocumentChunk,
    Modality,
    Provenance,
    RetrievalFilter,
    RetrievalResult,
)


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
        sparse_vectors: list[tuple[list[int], list[float]]] | None = None,
    ) -> int:
        """Upsert vectors and provenance payloads, returning the point count."""
        ...

    async def search_dense(
        self,
        *,
        vector: list[float],
        tenant_id: UUID,
        filters: RetrievalFilter | None = None,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Search named dense vectors with tenant and metadata filters."""
        ...

    async def search_sparse(
        self,
        *,
        indices: list[int],
        values: list[float],
        tenant_id: UUID,
        filters: RetrievalFilter | None = None,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Search named sparse vectors with tenant and metadata filters."""
        ...


class QdrantVectorIndex:
    """Qdrant adapter for dense vectors and provenance-filterable payloads."""

    def __init__(self, client: object, collection_name: str) -> None:
        self._client = client
        self._collection_name = collection_name

    async def ensure_collection(self, *, dimension: int) -> None:
        """Create a named dense+sparse collection when absent."""
        from qdrant_client.http import models

        exists = await self._client.collection_exists(collection_name=self._collection_name)  # type: ignore[attr-defined]
        if not exists:
            await self._client.create_collection(  # type: ignore[attr-defined]
                collection_name=self._collection_name,
                vectors_config={
                    "dense": models.VectorParams(size=dimension, distance=models.Distance.COSINE),
                },
                sparse_vectors_config={"sparse": models.SparseVectorParams()},
            )

    async def upsert_chunks(
        self,
        *,
        tenant_id: UUID,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        model_name: str,
        sparse_vectors: list[tuple[list[int], list[float]]] | None = None,
    ) -> int:
        """Write vectors with tenant and citation metadata as payload."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal lengths")
        if sparse_vectors is not None and len(chunks) != len(sparse_vectors):
            raise ValueError("chunks and sparse vectors must have equal lengths")
        from qdrant_client.http import models

        points = [
            models.PointStruct(
                id=str(chunk.chunk_id),
                vector=(
                    {
                        "dense": vector,
                        "sparse": models.SparseVector(
                            indices=sparse_vectors[index][0],
                            values=sparse_vectors[index][1],
                        ),
                    }
                    if sparse_vectors is not None
                    else vector
                ),
                payload={
                    "tenant_id": str(tenant_id),
                    "document_id": str(chunk.document_id),
                    "chunk_id": str(chunk.chunk_id),
                    "content": chunk.content,
                    "modality": chunk.modality.value,
                    "page_number": chunk.provenance.page_number,
                    "region_id": chunk.provenance.region_id,
                    "embedding_model": model_name,
                    "created_at": chunk.created_at.isoformat(),
                },
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        if points:
            await self._client.upsert(  # type: ignore[attr-defined]
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
        return len(points)

    async def search_dense(
        self,
        *,
        vector: list[float],
        tenant_id: UUID,
        filters: RetrievalFilter | None = None,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Query the named dense vector space and convert points to contracts."""
        return await self._search(
            query=vector,
            using="dense",
            source="dense_qdrant",
            tenant_id=tenant_id,
            filters=filters,
            limit=limit,
        )

    async def search_sparse(
        self,
        *,
        indices: list[int],
        values: list[float],
        tenant_id: UUID,
        filters: RetrievalFilter | None = None,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Query the named sparse vector space and convert points to contracts."""
        from qdrant_client.http import models

        return await self._search(
            query=models.SparseVector(indices=indices, values=values),
            using="sparse",
            source="sparse_qdrant",
            tenant_id=tenant_id,
            filters=filters,
            limit=limit,
        )

    async def _search(
        self,
        *,
        query: object,
        using: str,
        source: str,
        tenant_id: UUID,
        filters: RetrievalFilter | None,
        limit: int,
    ) -> list[RetrievalResult]:
        """Execute a tenant-filtered Qdrant query and normalize scored points."""
        if limit < 1:
            raise ValueError("limit must be positive")
        query_filter = self._build_filter(tenant_id=tenant_id, filters=filters)
        response = await self._client.query_points(  # type: ignore[attr-defined]
            collection_name=self._collection_name,
            query=query,
            using=using,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            self._point_to_result(cast(Any, point), source=source)
            for point in response.points
        ]

    @staticmethod
    def _build_filter(*, tenant_id: UUID, filters: RetrievalFilter | None) -> object:
        """Build a mandatory tenant condition plus optional metadata conditions."""
        from qdrant_client.http import models

        conditions = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=str(tenant_id)),
            )
        ]
        if filters is not None:
            for key, value in (
                ("document_id", filters.document_id),
                ("modality", filters.modality.value if filters.modality else None),
                ("page_number", filters.page_number),
            ):
                if value is not None:
                    conditions.append(
                        models.FieldCondition(key=key, match=models.MatchValue(value=str(value)))
                    )
        return models.Filter(must=cast(Any, conditions))

    @staticmethod
    def _point_to_result(point: object, *, source: str) -> RetrievalResult:
        """Convert a Qdrant scored point payload into a cited chunk contract."""
        payload = cast(dict[str, object], point.payload)  # type: ignore[attr-defined]
        document_id = UUID(str(payload["document_id"]))
        chunk_id = UUID(str(payload["chunk_id"]))
        page_number = payload.get("page_number")
        region_id = payload.get("region_id")
        page_number = int(str(page_number)) if page_number is not None else None
        region_id = str(region_id) if region_id is not None else None
        return RetrievalResult(
            chunk=DocumentChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                tenant_id=UUID(str(payload["tenant_id"])),
                content=str(payload["content"]),
                modality=Modality(str(payload["modality"])),
                provenance=Provenance(
                    document_id=document_id,
                    page_number=page_number,
                    region_id=region_id,
                    chunk_id=chunk_id,
                ),
                created_at=datetime.fromisoformat(str(payload["created_at"])),
            ),
            score=point.score,  # type: ignore[attr-defined]
            source=source,
        )
