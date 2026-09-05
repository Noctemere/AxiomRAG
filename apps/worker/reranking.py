from __future__ import annotations

import math
import re
from typing import Protocol

from packages.contracts.models import RetrievalResult


class Reranker(Protocol):
    """Provider-neutral boundary for reranking retrieved evidence."""

    model_name: str

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        limit: int,
    ) -> list[RetrievalResult]:
        """Return evidence ordered by query relevance."""
        ...


class LexicalReranker:
    """Deterministic local reranker for development and regression tests."""

    model_name = "local-lexical-reranker"

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        limit: int,
    ) -> list[RetrievalResult]:
        """Score query-term coverage and preserve original evidence metadata."""
        if limit < 1:
            raise ValueError("limit must be positive")
        query_terms = set(re.findall(r"\w+", query.lower()))
        rescored: list[RetrievalResult] = []
        for result in results:
            content_terms = set(re.findall(r"\w+", result.chunk.content.lower()))
            overlap = len(query_terms & content_terms)
            score = math.log1p(overlap) + result.score * 0.01
            rescored.append(result.model_copy(update={"score": score, "source": self.model_name}))
        return sorted(rescored, key=lambda result: result.score, reverse=True)[:limit]
