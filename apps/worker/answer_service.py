from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

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


class OpenAICompatibleAnswerGenerator:
    """Grounded answer adapter for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("answer API key must not be empty")
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._owns_client = client is None

    async def generate(self, query: str, evidence: list[RetrievalResult]) -> Answer:
        """Generate a grounded answer and reject citations absent from evidence."""
        if not evidence:
            return await ExtractiveAnswerGenerator().generate(query, evidence)
        context = "\n\n".join(
            f"[{index}] {result.chunk.content}" for index, result in enumerate(evidence, start=1)
        )
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model_name,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer only from the supplied evidence. "
                            "Cite sources as [1], [2], etc."
                        ),
                    },
                    {"role": "user", "content": f"Evidence:\n{context}\n\nQuestion: {query}"},
                ],
            },
        )
        response.raise_for_status()
        payload: Any = response.json()
        text = payload["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("answer provider returned empty content")
        citations = [
            Citation(
                source_name=f"document:{result.chunk.document_id}",
                quote=result.chunk.content,
                provenance=result.chunk.provenance,
            )
            for index, result in enumerate(evidence, start=1)
            if f"[{index}]" in text
        ]
        if not citations:
            raise ValueError("answer provider returned no valid evidence citations")
        return Answer(
            text=text,
            citations=citations,
            model=self.model_name,
            created_at=datetime.now(UTC),
        )

    async def aclose(self) -> None:
        """Close the HTTP client when this generator created it."""
        if self._owns_client:
            await self._client.aclose()


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
