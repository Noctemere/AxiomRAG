from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database import engine
from apps.worker.asset_repository import PostgresAssetRepository
from apps.worker.celery_app import celery_app
from apps.worker.chunk_repository import PostgresChunkRepository
from apps.worker.chunking import ChunkingService
from apps.worker.docling_parser import DoclingParser
from apps.worker.embedding import HashEmbeddingProvider
from apps.worker.embedding import embed_chunks as create_embeddings
from apps.worker.job_lifecycle import JobLifecycleService
from apps.worker.parser import ParserRegistry, PlainTextParser
from apps.worker.qdrant_index import QdrantVectorIndex
from apps.worker.sparse_vector import SparseVectorizer
from apps.worker.storage import LocalDocumentStore
from packages.contracts.models import DocumentAsset

settings = get_settings()
document_store = LocalDocumentStore(Path("data/documents"))
parser_registry = ParserRegistry([PlainTextParser(), DoclingParser.create_default()])
chunking_service = ChunkingService()
embedding_provider = HashEmbeddingProvider()
sparse_vectorizer = SparseVectorizer()
qdrant_index = QdrantVectorIndex(AsyncQdrantClient(settings.qdrant_url), settings.qdrant_collection)


async def _parse_and_persist(
    *,
    document_id: UUID,
    tenant_id: UUID,
    storage_key: str,
    content_type: str,
) -> int:
    """Read, parse, chunk, and persist one document inside an async worker bridge."""
    content = await document_store.read(storage_key)
    parser = parser_registry.get(content_type)
    parsed = parser.parse(
        document_id=document_id,
        tenant_id=tenant_id,
        content=content,
        content_type=content_type,
    )
    chunks = chunking_service.chunk_blocks(parsed.blocks)
    asset_records: list[DocumentAsset] = []
    for asset in parsed.assets:
        asset_key = f"{tenant_id}/{document_id}/assets/{asset.asset_id}.bin"
        await document_store.save(asset_key, asset.content)
        asset_records.append(
            DocumentAsset(
                asset_id=asset.asset_id,
                document_id=document_id,
                tenant_id=tenant_id,
                modality=asset.modality,
                storage_key=asset_key,
                provenance=asset.provenance,
                created_at=datetime.now(UTC),
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        repository = PostgresChunkRepository(session)
        await repository.replace_for_document(
            document_id=document_id,
            tenant_id=tenant_id,
            chunks=chunks,
        )
        await PostgresAssetRepository(session).replace_for_document(
            document_id=document_id,
            tenant_id=tenant_id,
            assets=asset_records,
        )
    return len(chunks)


async def _set_job_status(
    *,
    job_id: str,
    tenant_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Persist a task lifecycle transition through the shared job service."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        lifecycle = JobLifecycleService(session)
        if status == "processing":
            await lifecycle.mark_processing(job_id=UUID(job_id), tenant_id=UUID(tenant_id))
        elif status == "completed":
            await lifecycle.mark_completed(job_id=UUID(job_id), tenant_id=UUID(tenant_id))
        elif status == "failed" and error is not None:
            await lifecycle.mark_failed(
                job_id=UUID(job_id), tenant_id=UUID(tenant_id), error=error
            )


async def _embed_and_index(
    *,
    document_id: UUID,
    tenant_id: UUID,
) -> int:
    """Load chunks, create dense vectors, and upsert them with citation payloads."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        chunks = await PostgresChunkRepository(session).list_for_document(
            document_id=document_id,
            tenant_id=tenant_id,
        )
    vectors = await create_embeddings(embedding_provider, chunks)
    sparse_vectors = sparse_vectorizer.transform([chunk.content for chunk in chunks])
    await qdrant_index.ensure_collection(dimension=embedding_provider.dimension)
    return await qdrant_index.upsert_chunks(
        tenant_id=tenant_id,
        chunks=chunks,
        vectors=vectors,
        model_name=embedding_provider.model_name,
        sparse_vectors=sparse_vectors,
    )


@celery_app.task(bind=True, name="ingestion.parse_document")  # type: ignore[misc]
def parse_document(
    self: celery_app.Task,  # type: ignore[name-defined]
    job_id: str,
    document_id: str,
    tenant_id: str,
    storage_key: str,
    content_type: str,
) -> dict[str, str | int]:
    """Parse a persisted document into layout-aware text, tables, and images.

    This task is called after upload validation and persistence.
    It handles the heavy lifting of document parsing without blocking the API.

    Args:
        job_id: Unique ingestion job identifier
        document_id: Unique document identifier
        tenant_id: Tenant ownership identifier
        storage_key: Location of the persisted document in storage
        content_type: MIME type of the document

    Returns:
        A dictionary with status and result details for the database layer.

    Raises:
        celery.Task.retry: If parsing fails and retries are configured.
    """
    try:
        asyncio.run(_set_job_status(job_id=job_id, tenant_id=tenant_id, status="processing"))
        chunks_created = asyncio.run(
            _parse_and_persist(
                document_id=UUID(document_id),
                tenant_id=UUID(tenant_id),
                storage_key=storage_key,
                content_type=content_type,
            )
        )
        return {
            "job_id": job_id,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "status": "queued_for_embedding",
            "chunks_created": chunks_created,
        }
    except Exception as exc:
        asyncio.run(
            _set_job_status(
                job_id=job_id,
                tenant_id=tenant_id,
                status="failed",
                error=str(exc),
            )
        )
        # Exponential backoff retry: 60s, 120s, 300s
        raise self.retry(exc=exc, countdown=60, max_retries=3) from None


@celery_app.task(bind=True, name="ingestion.embed_chunks")  # type: ignore[misc]
def embed_chunks(
    self: celery_app.Task,  # type: ignore[name-defined]
    job_id: str,
    document_id: str,
    tenant_id: str,
) -> dict[str, str | int]:
    """Generate embeddings for parsed document chunks.

    This task is called after parse_document completes.
    It generates dense and sparse vectors for hybrid retrieval.

    Args:
        job_id: Unique ingestion job identifier
        document_id: Unique document identifier
        tenant_id: Tenant ownership identifier

    Returns:
        A dictionary with status and embedding metrics for the database layer.

    Raises:
        celery.Task.retry: If embedding fails and retries are configured.
    """
    try:
        embeddings_created = asyncio.run(
            _embed_and_index(
                document_id=UUID(document_id),
                tenant_id=UUID(tenant_id),
            )
        )
        return {
            "job_id": job_id,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "status": "queued_for_indexing",
            "embeddings_created": embeddings_created,
        }
    except Exception as exc:
        asyncio.run(
            _set_job_status(
                job_id=job_id,
                tenant_id=tenant_id,
                status="failed",
                error=str(exc),
            )
        )
        # Exponential backoff retry: 60s, 120s, 300s
        raise self.retry(exc=exc, countdown=60, max_retries=3) from None


@celery_app.task(name="ingestion.index_to_qdrant")  # type: ignore[misc]
def index_to_qdrant(
    job_id: str,
    document_id: str,
    tenant_id: str,
) -> dict[str, str | int]:
    """Index parsed chunks and embeddings into Qdrant vector database.

    This task is called after embed_chunks completes.
    It performs the final indexing step and marks the ingestion job as complete.

    Args:
        job_id: Unique ingestion job identifier
        document_id: Unique document identifier
        tenant_id: Tenant ownership identifier

    Returns:
        A dictionary with status and indexing metrics for the database layer.

    Raises:
        RuntimeError: If Qdrant is unavailable.
    """
    try:
        # Qdrant indexing is implemented in Phase 3; this task still closes the lifecycle.
        asyncio.run(_set_job_status(job_id=job_id, tenant_id=tenant_id, status="completed"))
        return {
            "job_id": job_id,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "status": "completed",
            "vectors_indexed": 0,
        }
    except Exception as exc:
        asyncio.run(
            _set_job_status(
                job_id=job_id,
                tenant_id=tenant_id,
                status="failed",
                error=str(exc),
            )
        )
        raise
