from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.worker.embedding import HashEmbeddingProvider, embed_chunks
from packages.contracts.models import DocumentChunk, Modality, Provenance


def make_chunk(content: str) -> DocumentChunk:
    document_id = uuid4()
    return DocumentChunk(
        chunk_id=uuid4(),
        document_id=document_id,
        tenant_id=uuid4(),
        content=content,
        modality=Modality.TEXT,
        provenance=Provenance(document_id=document_id, page_number=1),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_hash_embeddings_are_normalized_and_deterministic() -> None:
    """Verify the development provider returns stable unit-length vectors."""
    provider = HashEmbeddingProvider(dimension=16)
    first = await provider.embed(["same content"])
    second = await provider.embed(["same content"])

    assert first == second
    assert len(first) == 1
    assert len(first[0]) == 16
    assert sum(value * value for value in first[0]) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_embed_chunks_preserves_input_order() -> None:
    """Verify vectors correspond to chunks in their original order."""
    provider = HashEmbeddingProvider(dimension=16)
    chunks = [make_chunk("first"), make_chunk("second")]
    vectors = await embed_chunks(provider, chunks)

    assert len(vectors) == 2
    assert vectors[0] != vectors[1]


def test_hash_provider_rejects_tiny_dimensions() -> None:
    """Verify invalid vector configuration fails early."""
    with pytest.raises(ValueError, match="at least 8"):
        HashEmbeddingProvider(dimension=4)
