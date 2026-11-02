from __future__ import annotations

from apps.worker.embedding import EmbeddingProvider
from apps.worker.fusion import ReciprocalRankFusion
from apps.worker.qdrant_index import QdrantVectorIndex
from apps.worker.reranking import Reranker
from apps.worker.sparse_vector import SparseVectorizer
from packages.contracts.models import Query, RetrievalFilter, RetrievalResult


class QdrantHybridRetriever:
    """Retrieve dense+sparse Qdrant evidence, fuse it, and optionally rerank it."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        sparse_vectorizer: SparseVectorizer,
        index: QdrantVectorIndex,
        fusion: ReciprocalRankFusion | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._sparse_vectorizer = sparse_vectorizer
        self._index = index
        self._fusion = fusion or ReciprocalRankFusion()
        self._reranker = reranker

    async def retrieve(
        self,
        query: Query,
        *,
        filters: RetrievalFilter | None,
        limit: int,
    ) -> list[RetrievalResult]:
        """Run dense+sparse retrieval with mandatory tenant filtering."""
        if limit < 1:
            raise ValueError("limit must be positive")
        dense = (await self._embedding_provider.embed([query.text]))[0]
        sparse_indices, sparse_values = self._sparse_vectorizer.transform([query.text])[0]
        dense_results = await self._index.search_dense(
            vector=dense,
            tenant_id=query.tenant_id,
            filters=filters,
            limit=limit,
        )
        sparse_results = await self._index.search_sparse(
            indices=sparse_indices,
            values=sparse_values,
            tenant_id=query.tenant_id,
            filters=filters,
            limit=limit,
        )
        fused = self._fusion.fuse([dense_results, sparse_results], limit=limit)
        if self._reranker is None:
            return fused
        return await self._reranker.rerank(query.text, fused, limit=limit)
