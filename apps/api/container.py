from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from apps.api.config import Settings
from apps.worker.answer_service import ExtractiveAnswerGenerator, OpenAICompatibleAnswerGenerator
from apps.worker.embedding import HashEmbeddingProvider, OpenAICompatibleEmbeddingProvider
from apps.worker.graph_adapters import AnswerServiceAdapter, UnavailableSqlExecutor
from apps.worker.orchestration import OrchestrationGraph
from apps.worker.qdrant_index import QdrantVectorIndex
from apps.worker.redis_cache import RedisSemanticCache
from apps.worker.reranking import LexicalReranker
from apps.worker.retriever import QdrantHybridRetriever
from apps.worker.sparse_vector import SparseVectorizer


@dataclass
class ApplicationContainer:
    """Own configured retrieval, answer, cache, and graph dependencies."""

    graph: object
    qdrant: AsyncQdrantClient
    redis: Redis
    embedding: object

    @classmethod
    def create(cls, settings: Settings) -> ApplicationContainer:
        """Build the local or configured provider graph without performing network calls."""
        qdrant = AsyncQdrantClient(settings.qdrant_url)
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        if settings.embedding_api_key:
            embedding = OpenAICompatibleEmbeddingProvider(
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_base_url,
                model_name=settings.embedding_model,
                dimension=settings.embedding_dimension,
                batch_size=settings.embedding_batch_size,
            )
            embedding_model = settings.embedding_model
        else:
            embedding = HashEmbeddingProvider(dimension=128)
            embedding_model = embedding.model_name
        index = QdrantVectorIndex(qdrant, settings.qdrant_collection)
        retriever = QdrantHybridRetriever(
            embedding_provider=embedding,
            sparse_vectorizer=SparseVectorizer(),
            index=index,
            reranker=LexicalReranker(),
        )
        generator = (
            OpenAICompatibleAnswerGenerator(
                api_key=settings.answer_api_key,
                base_url=settings.answer_base_url,
                model_name=settings.answer_model,
            )
            if settings.answer_api_key
            else ExtractiveAnswerGenerator()
        )
        answerer = AnswerServiceAdapter(
            generator=generator,
            cache=RedisSemanticCache(redis),
            embedding_model=embedding_model,
            index_version="phase3",
            ttl_seconds=settings.answer_cache_ttl_seconds,
        )
        graph = OrchestrationGraph(
            retriever=retriever,
            sql_executor=UnavailableSqlExecutor(),
            answerer=answerer,
        ).compile()
        return cls(graph=graph, qdrant=qdrant, redis=redis, embedding=embedding)

    async def close(self) -> None:
        """Close owned external clients during application shutdown."""
        await self.qdrant.close()
        await self.redis.aclose()
        close = getattr(self.embedding, "aclose", None)
        if close is not None:
            await close()
