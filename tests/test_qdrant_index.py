from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest

from apps.worker.qdrant_index import QdrantVectorIndex
from packages.contracts.models import (
    DocumentChunk,
    Modality,
    Provenance,
    RetrievalFilter,
)


def make_chunk() -> DocumentChunk:
    document_id = uuid4()
    return DocumentChunk(
        chunk_id=uuid4(),
        document_id=document_id,
        tenant_id=uuid4(),
        content="indexed content",
        modality=Modality.TEXT,
        provenance=Provenance(document_id=document_id, page_number=2, region_id="r1"),
        created_at=datetime.now(UTC),
    )


class FakeQdrantClient:
    """Minimal async Qdrant client double that records collection and point writes."""

    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.upserts: list[dict[str, object]] = []
        self.queries: list[dict[str, object]] = []

    async def collection_exists(self, *, collection_name: str) -> bool:
        return collection_name in self.collections

    async def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: object,
        sparse_vectors_config: object,
    ) -> None:
        self.collections.add(collection_name)

    async def upsert(
        self,
        *,
        collection_name: str,
        points: list[object],
        wait: bool,
    ) -> None:
        self.upserts.append(
            {"collection_name": collection_name, "points": points, "wait": wait}
        )

    async def query_points(self, **kwargs: object) -> object:
        self.queries.append(kwargs)
        upsert = cast(Any, self.upserts[0])
        point = upsert["points"][0]
        return type("Response", (), {"points": [type("Point", (), {
            "payload": point.payload,
            "score": 0.91,
        })()]})()


@pytest.mark.asyncio
async def test_qdrant_index_creates_collection_and_preserves_payload() -> None:
    """Verify collection setup and citation payload construction."""
    client = FakeQdrantClient()
    index = QdrantVectorIndex(client, "documents")
    chunk = make_chunk()

    await index.ensure_collection(dimension=16)
    count = await index.upsert_chunks(
        tenant_id=chunk.tenant_id,
        chunks=[chunk],
        vectors=[[0.5] * 16],
        model_name="test-model",
        sparse_vectors=[([3, 9], [1.0, 2.0])],
    )

    assert count == 1
    assert client.collections == {"documents"}
    upsert = cast(Any, client.upserts[0])
    point = upsert["points"][0]
    assert point.payload["tenant_id"] == str(chunk.tenant_id)
    assert point.payload["page_number"] == 2
    assert point.payload["embedding_model"] == "test-model"
    assert "created_at" in point.payload
    assert "dense" in point.vector
    assert point.vector["sparse"].indices == [3, 9]


@pytest.mark.asyncio
async def test_qdrant_index_rejects_mismatched_vectors() -> None:
    """Verify chunks and vectors cannot silently become misaligned."""
    index = QdrantVectorIndex(FakeQdrantClient(), "documents")
    with pytest.raises(ValueError, match="equal lengths"):
        await index.upsert_chunks(
            tenant_id=uuid4(),
            chunks=[make_chunk()],
            vectors=[],
            model_name="test-model",
        )


@pytest.mark.asyncio
async def test_qdrant_dense_query_enforces_tenant_and_filters() -> None:
    """Verify dense queries use the named vector and metadata filter."""
    client = FakeQdrantClient()
    index = QdrantVectorIndex(client, "documents")
    chunk = make_chunk()
    await index.upsert_chunks(
        tenant_id=chunk.tenant_id,
        chunks=[chunk],
        vectors=[[0.5] * 16],
        model_name="test-model",
        sparse_vectors=[([3], [1.0])],
    )

    results = await index.search_dense(
        vector=[0.5] * 16,
        tenant_id=chunk.tenant_id,
        filters=RetrievalFilter(document_id=chunk.document_id, page_number=2),
    )

    assert results[0].source == "dense_qdrant"
    assert results[0].chunk.chunk_id == chunk.chunk_id
    query = cast(Any, client.queries[0])
    assert query["using"] == "dense"
    assert query["query_filter"].must[0].key == "tenant_id"
    assert len(query["query_filter"].must) == 3


@pytest.mark.asyncio
async def test_qdrant_sparse_query_uses_sparse_vector() -> None:
    """Verify sparse queries construct a Qdrant SparseVector and normalize results."""
    client = FakeQdrantClient()
    index = QdrantVectorIndex(client, "documents")
    chunk = make_chunk()
    await index.upsert_chunks(
        tenant_id=chunk.tenant_id,
        chunks=[chunk],
        vectors=[[0.5] * 16],
        model_name="test-model",
        sparse_vectors=[([3], [1.0])],
    )

    results = await index.search_sparse(
        indices=[3],
        values=[1.0],
        tenant_id=chunk.tenant_id,
    )

    assert results[0].source == "sparse_qdrant"
    query = cast(Any, client.queries[0])
    assert query["using"] == "sparse"
    assert query["query"].indices == [3]
