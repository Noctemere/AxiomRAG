from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from packages.contracts.models import RetrievalResult


@dataclass(frozen=True)
class RetrievalExample:
    """One deterministic retrieval benchmark case."""

    query: str
    tenant_id: UUID
    relevant_chunk_ids: frozenset[UUID]


def recall_at_k(results: list[RetrievalResult], relevant: frozenset[UUID], k: int) -> float:
    """Measure the fraction of relevant chunks found in the first k results."""
    if not relevant:
        return 1.0
    found = {result.chunk.chunk_id for result in results[:k]}
    return len(found & relevant) / len(relevant)


def reciprocal_rank(results: list[RetrievalResult], relevant: frozenset[UUID]) -> float:
    """Return reciprocal rank of the first relevant result, or zero."""
    for rank, result in enumerate(results, start=1):
        if result.chunk.chunk_id in relevant:
            return 1 / rank
    return 0.0


def mean_reciprocal_rank(
    cases: list[tuple[list[RetrievalResult], frozenset[UUID]]],
) -> float:
    """Average reciprocal rank across deterministic benchmark cases."""
    if not cases:
        return 0.0
    return sum(reciprocal_rank(results, relevant) for results, relevant in cases) / len(cases)
