from __future__ import annotations

import asyncio
from typing import Any

from packages.contracts.models import RetrievalResult


class FlashRankReranker:
    """Local cross-encoder reranker using FlashRank in a worker thread."""

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2") -> None:
        from flashrank import Ranker

        self.model_name = model_name
        self._ranker = Ranker(model_name=model_name)

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        limit: int,
    ) -> list[RetrievalResult]:
        """Score retrieved passages with FlashRank without blocking the event loop."""
        if limit < 1:
            raise ValueError("limit must be positive")
        if not results:
            return []
        return await asyncio.to_thread(self._rerank_sync, query, results, limit)

    def _rerank_sync(
        self,
        query: str,
        results: list[RetrievalResult],
        limit: int,
    ) -> list[RetrievalResult]:
        from flashrank import RerankRequest

        passages = [
            {"id": index, "text": result.chunk.content, "meta": {"result": result}}
            for index, result in enumerate(results)
        ]
        ranked: list[Any] = self._ranker.rerank(RerankRequest(query=query, passages=passages))
        reranked: list[RetrievalResult] = []
        for item in ranked[:limit]:
            original = item.get("meta", {}).get("result")
            if isinstance(original, RetrievalResult):
                reranked.append(
                    original.model_copy(
                        update={
                            "score": float(item.get("relevance_score", 0.0)),
                            "source": self.model_name,
                        }
                    )
                )
        return reranked
