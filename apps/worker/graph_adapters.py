from __future__ import annotations

from datetime import UTC, datetime

from apps.worker.answer_service import AnswerGenerator, AnswerService
from apps.worker.semantic_cache import CacheKey, SemanticCache
from packages.contracts.models import Answer, Query, RetrievalResult


class AnswerServiceAdapter:
    """Adapt the cache-aware answer service to the LangGraph Answerer port."""

    def __init__(
        self,
        *,
        generator: AnswerGenerator,
        cache: SemanticCache,
        embedding_model: str,
        index_version: str,
        ttl_seconds: int,
    ) -> None:
        self._service = AnswerService(generator, cache, ttl_seconds=ttl_seconds)
        self._embedding_model = embedding_model
        self._index_version = index_version

    async def answer(
        self,
        query: Query,
        evidence: list[RetrievalResult],
        sql_rows: list[dict[str, object]],
    ) -> Answer:
        """Generate or retrieve a tenant-scoped cached answer."""
        answer, _cache_hit = await self._service.answer(
            query,
            evidence,
            cache_key=CacheKey(
                tenant_id=query.tenant_id,
                query=query.text,
                filters=None,
                embedding_model=self._embedding_model,
                index_version=self._index_version,
            ),
        )
        if sql_rows and not evidence:
            return Answer(
                text=f"Structured query returned {len(sql_rows)} row(s).",
                citations=[],
                model=answer.model,
                created_at=datetime.now(UTC),
            )
        return answer


class UnavailableSqlExecutor:
    """Explicit adapter used until a configured Text-to-SQL generator is installed."""

    async def execute(self, query: Query) -> list[dict[str, object]]:
        """Fail clearly instead of executing ungenerated SQL."""
        raise RuntimeError("structured SQL execution is not configured")
