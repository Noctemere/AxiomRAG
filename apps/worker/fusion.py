from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from packages.contracts.models import RetrievalResult


class ReciprocalRankFusion:
    """Combine ranked retrieval lists without assuming comparable raw scores."""

    def __init__(self, rank_constant: int = 60) -> None:
        if rank_constant < 1:
            raise ValueError("rank_constant must be positive")
        self._rank_constant = rank_constant

    def fuse(
        self,
        result_lists: Iterable[list[RetrievalResult]],
        *,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Fuse rankings and retain the best available evidence for each chunk."""
        if limit < 1:
            raise ValueError("limit must be positive")
        fused_scores: defaultdict[UUID, float] = defaultdict(float)
        best_results: dict[UUID, RetrievalResult] = {}
        for results in result_lists:
            for rank, result in enumerate(results, start=1):
                chunk_id = result.chunk.chunk_id
                fused_scores[chunk_id] += 1 / (self._rank_constant + rank)
                current = best_results.get(chunk_id)
                if current is None or result.score > current.score:
                    best_results[chunk_id] = result
        ranked = sorted(
            best_results.values(),
            key=lambda result: fused_scores[result.chunk.chunk_id],
            reverse=True,
        )
        return [
            result.model_copy(
                update={
                    "score": fused_scores[result.chunk.chunk_id],
                    "source": "rrf_hybrid",
                }
            )
            for result in ranked[:limit]
        ]
