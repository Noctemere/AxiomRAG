from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from apps.worker.answer_service import OpenAICompatibleAnswerGenerator
from apps.worker.redis_cache import RedisSemanticCache
from apps.worker.semantic_cache import CacheKey
from packages.contracts.models import Answer, DocumentChunk, Modality, Provenance, RetrievalResult


def make_result() -> RetrievalResult:
    document_id = uuid4()
    return RetrievalResult(
        chunk=DocumentChunk(
            chunk_id=uuid4(),
            document_id=document_id,
            tenant_id=uuid4(),
            content="Grounded evidence",
            modality=Modality.TEXT,
            provenance=Provenance(document_id=document_id, page_number=1),
            created_at=datetime.now(UTC),
        ),
        score=1.0,
        source="test",
    )


@pytest.mark.asyncio
async def test_openai_answer_generator_requires_citation() -> None:
    """Verify grounded answer responses without evidence markers are rejected."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Unsupported answer"}}]},
            )
        )
    )
    generator = OpenAICompatibleAnswerGenerator(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
        client=client,
    )
    with pytest.raises(ValueError, match="no valid evidence citations"):
        await generator.generate("question", [make_result()])
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_answer_generator_maps_citation_marker() -> None:
    """Verify valid evidence markers become typed citations."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Answer [1]"}}]},
            )
        )
    )
    generator = OpenAICompatibleAnswerGenerator(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="test-model",
        client=client,
    )
    answer = await generator.generate("question", [make_result()])
    assert answer.text == "Answer [1]"
    assert len(answer.citations) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_redis_cache_serializes_answer_and_ttl() -> None:
    """Verify Redis cache writes JSON with the requested expiry."""
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.expiry = None

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def set(self, key: str, value: str, *, ex: int) -> None:
            self.values[key] = value
            self.expiry = ex

    client = FakeRedis()
    cache = RedisSemanticCache(client)  # type: ignore[arg-type]
    key = CacheKey(uuid4(), "query", None, "model", "v1")
    answer = Answer(text="answer", citations=[], model="test", created_at=datetime.now(UTC))

    await cache.put(key, answer, 60)
    assert await cache.get(key) == answer
    assert client.expiry == 60
