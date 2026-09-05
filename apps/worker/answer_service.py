from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from apps.worker.semantic_cache import CacheKey, SemanticCache
from packages.contracts.models import Answer, Citation, Query, RetrievalResult


class AnswerGenerator(Protocol):
    """Provider-neutral boundary for grounded answer generation."""

    model_name: str

    async def generate(self, query: str, evidence: list[RetrievalResult]) -> Answer:
        """Generate an answer that cites only supplied evidence."""
        ...


class ExtractiveAnswerGenerator:
    """Safe local answer generator that never invents unsupported content."""

    model_name = "local-extractive"

    async def generate(self, query: str, evidence: list[RetrievalResult]) -> Answer:
        """Return concise evidence excerpts with one citation per source chunk."""
        if not evidence:
            return Answer(
                text="I could not find supporting evidence for this question.",
                citations=[],
                model=self.model_name,
                created_at=datetime.now(UTC),
            )
        citations = [
            Citation(
                source_name=f"document:{result.chunk.document_id}",
                quote=result.chunk.content,
                provenance=result.chunk.provenance,
            )
            for result in evidence
        ]
        text = "\n\n".join(citation.quote for citation in citations)
        return Answer(
            text=text,
            citations=citations,
            model=self.model_name,
            created_at=datetime.now(UTC),
        )


class AnswerService:
    """Coordinates cache lookup, grounded generation, and cache writes."""

    def __init__(
        self,
        generator: AnswerGenerator,
        cache: SemanticCache,
        *,
        ttl_seconds: int = 300,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("answer cache TTL must be positive")
        self._generator = generator
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def answer(
        self,
        query: Query,
        evidence: list[RetrievalResult],
        *,
        cache_key: CacheKey,
    ) -> tuple[Answer, bool]:
        """Return an answer and whether it came from the authorized cache."""
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached, True
        answer = await self._generator.generate(query.text, evidence)
        await self._cache.put(cache_key, answer, self._ttl_seconds)
        return answer, False
