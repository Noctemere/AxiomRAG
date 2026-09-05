from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from apps.worker.answer_service import AnswerService, ExtractiveAnswerGenerator
from apps.worker.reranking import LexicalReranker
from apps.worker.semantic_cache import CacheKey, InMemorySemanticCache
from packages.contracts.models import (
    DocumentChunk,
    Modality,
    Provenance,
    Query,
    RetrievalFilter,
    RetrievalResult,
)
from packages.evals.metrics import mean_reciprocal_rank, recall_at_k


def make_result(content: str, tenant_id: UUID | None = None) -> RetrievalResult:
    document_id = uuid4()
    chunk = DocumentChunk(
        chunk_id=uuid4(),
        document_id=document_id,
        tenant_id=tenant_id or uuid4(),
        content=content,
        modality=Modality.TEXT,
        provenance=Provenance(document_id=document_id, page_number=1),
        created_at=datetime.now(UTC),
    )
    return RetrievalResult(chunk=chunk, score=0.1, source="test")


@pytest.mark.asyncio
async def test_reranker_promotes_term_overlap() -> None:
    """Verify lexical reranking improves query-term ordering."""
    reranker = LexicalReranker()
    results = await reranker.rerank(
        "vector search",
        [make_result("unrelated prose"), make_result("vector search evidence")],
        limit=2,
    )
    assert "vector search" in results[0].chunk.content
    assert results[0].source == reranker.model_name


@pytest.mark.asyncio
async def test_semantic_cache_is_tenant_scoped() -> None:
    """Verify equivalent queries cannot share answers across tenants."""
    tenant_a, tenant_b = uuid4(), uuid4()
    cache = InMemorySemanticCache()
    answer, _ = await AnswerService(ExtractiveAnswerGenerator(), cache).answer(
        Query(text="Where?", tenant_id=tenant_a),
        [make_result("Evidence", tenant_a)],
        cache_key=CacheKey(tenant_a, "Where?", None, "model", "v1"),
    )
    assert await cache.get(CacheKey(tenant_a, "where?", None, "model", "v1")) == answer
    assert await cache.get(CacheKey(tenant_b, "where?", None, "model", "v1")) is None


@pytest.mark.asyncio
async def test_answer_has_only_evidence_citations() -> None:
    """Verify extractive answers cite every returned evidence chunk."""
    result = make_result("Grounded source text")
    answer = await ExtractiveAnswerGenerator().generate("question", [result])
    assert answer.text == "Grounded source text"
    assert len(answer.citations) == 1
    assert answer.citations[0].provenance == result.chunk.provenance


def test_retrieval_metrics_are_deterministic() -> None:
    """Verify recall and MRR calculations used for regression gates."""
    first, second = make_result("first"), make_result("second")
    relevant = frozenset({second.chunk.chunk_id})
    results = [first, second]
    assert recall_at_k(results, relevant, 2) == 1.0
    assert mean_reciprocal_rank([(results, relevant)]) == 0.5


def test_cache_key_includes_filters_and_model_version() -> None:
    """Verify retrieval configuration changes invalidate cached answers."""
    tenant = uuid4()
    base = CacheKey(tenant, "query", None, "model-a", "v1")
    changed = CacheKey(
        tenant,
        "query",
        RetrievalFilter(page_number=2),
        "model-a",
        "v1",
    )
    assert base.value() != changed.value()
