from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from apps.worker.fusion import ReciprocalRankFusion
from apps.worker.sparse_retrieval import Bm25Index
from packages.contracts.models import DocumentChunk, Modality, Provenance, RetrievalResult


def make_chunk(content: str, tenant_id: UUID) -> DocumentChunk:
    document_id = uuid4()
    return DocumentChunk(
        chunk_id=uuid4(),
        document_id=document_id,
        tenant_id=tenant_id,
        content=content,
        modality=Modality.TEXT,
        provenance=Provenance(document_id=document_id, page_number=1),
        created_at=datetime.now(UTC),
    )


def test_bm25_ranks_matching_terms_and_filters_tenant() -> None:
    """Verify lexical relevance and tenant isolation."""
    tenant_id = uuid4()
    other_tenant = uuid4()
    matching = make_chunk("PostgreSQL vector search", tenant_id)
    weak = make_chunk("PostgreSQL administration", tenant_id)
    hidden = make_chunk("PostgreSQL vector search", other_tenant)
    index = Bm25Index()
    index.add([matching, weak, hidden])

    results = index.search(query="vector search", tenant_id=tenant_id)

    assert results[0].chunk.chunk_id == matching.chunk_id
    assert all(result.chunk.tenant_id == tenant_id for result in results)
    assert all(result.source == "sparse_bm25" for result in results)


def test_bm25_handles_empty_query() -> None:
    """Verify punctuation-only queries return no false matches."""
    index = Bm25Index()
    assert index.search(query="...", tenant_id=uuid4()) == []


def test_rrf_promotes_results_present_in_both_rankings() -> None:
    """Verify overlap receives a larger fused score than one-list results."""
    tenant_id = uuid4()
    shared = make_chunk("shared", tenant_id)
    dense_only = make_chunk("dense", tenant_id)
    sparse_only = make_chunk("sparse", tenant_id)
    dense = [
        RetrievalResult(chunk=shared, score=0.8, source="dense"),
        RetrievalResult(chunk=dense_only, score=0.7, source="dense"),
    ]
    sparse = [
        RetrievalResult(chunk=shared, score=4.0, source="sparse_bm25"),
        RetrievalResult(chunk=sparse_only, score=3.0, source="sparse_bm25"),
    ]

    results = ReciprocalRankFusion(rank_constant=1).fuse([dense, sparse])

    assert results[0].chunk.chunk_id == shared.chunk_id
    assert results[0].source == "rrf_hybrid"
    assert results[0].score > results[1].score


def test_rrf_rejects_invalid_limit() -> None:
    """Verify invalid result limits fail early."""
    with pytest.raises(ValueError, match="positive"):
        ReciprocalRankFusion().fuse([], limit=0)