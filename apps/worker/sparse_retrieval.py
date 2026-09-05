from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from packages.contracts.models import DocumentChunk, RetrievalResult


@dataclass(frozen=True)
class SparseDocument:
    """Token statistics cached for one chunk in the sparse index."""

    chunk: DocumentChunk
    term_frequencies: Counter[str]
    length: int


class Bm25Index:
    """In-memory BM25 index for deterministic local sparse retrieval."""

    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self._k1 = k1
        self._b = b
        self._documents: dict[UUID, SparseDocument] = {}
        self._document_frequency: Counter[str] = Counter()

    def add(self, chunks: Iterable[DocumentChunk]) -> None:
        """Add or replace chunks and rebuild document-frequency statistics."""
        for chunk in chunks:
            tokens = self._tokenize(chunk.content)
            self._documents[chunk.chunk_id] = SparseDocument(
                chunk=chunk,
                term_frequencies=Counter(tokens),
                length=len(tokens),
            )
        self._rebuild_document_frequency()

    def search(
        self,
        *,
        query: str,
        tenant_id: UUID,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Return tenant-filtered chunks ranked by BM25 score."""
        if limit < 1:
            raise ValueError("limit must be positive")
        query_terms = self._tokenize(query)
        if not query_terms:
            return []
        average_length = self._average_document_length()
        total_documents = len(self._documents)
        scored: list[RetrievalResult] = []
        for document in self._documents.values():
            if document.chunk.tenant_id != tenant_id:
                continue
            score = self._score(
                query_terms=query_terms,
                document=document,
                average_length=average_length,
                total_documents=total_documents,
            )
            if score > 0:
                scored.append(
                    RetrievalResult(
                        chunk=document.chunk,
                        score=score,
                        source="sparse_bm25",
                    )
                )
        return sorted(scored, key=lambda result: result.score, reverse=True)[:limit]

    def _score(
        self,
        *,
        query_terms: list[str],
        document: SparseDocument,
        average_length: float,
        total_documents: int,
    ) -> float:
        score = 0.0
        for term in query_terms:
            frequency = document.term_frequencies.get(term, 0)
            if not frequency:
                continue
            document_frequency = self._document_frequency[term]
            inverse_frequency = math.log(
                1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            length_normalizer = 1 - self._b + self._b * document.length / average_length
            score += inverse_frequency * (
                frequency * (self._k1 + 1) / (frequency + self._k1 * length_normalizer)
            )
        return score

    def _rebuild_document_frequency(self) -> None:
        self._document_frequency.clear()
        for document in self._documents.values():
            self._document_frequency.update(document.term_frequencies.keys())

    def _average_document_length(self) -> float:
        if not self._documents:
            return 1.0
        return max(
            1.0,
            sum(document.length for document in self._documents.values()) / len(self._documents),
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())
