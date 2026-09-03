from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import engine
from apps.worker.celery_app import celery_app
from apps.worker.chunk_repository import PostgresChunkRepository
from apps.worker.chunking import ChunkingService
from apps.worker.docling_parser import DoclingParser
from apps.worker.parser import ParserRegistry, PlainTextParser
from apps.worker.storage import LocalDocumentStore

document_store = LocalDocumentStore(Path("data/documents"))
parser_registry = ParserRegistry([PlainTextParser(), DoclingParser.create_default()])
chunking_service = ChunkingService()


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
    blocks = parser.parse(
        document_id=document_id,
        tenant_id=tenant_id,
        content=content,
        content_type=content_type,
    )
    chunks = chunking_service.chunk_blocks(blocks)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        repository = PostgresChunkRepository(session)
        await repository.replace_for_document(
            document_id=document_id,
            tenant_id=tenant_id,
            chunks=chunks,
        )
    return len(chunks)


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
        # Placeholder: embedding logic will be implemented in Phase 3.
        # Future work will integrate embedding adapters and batch processing.
        return {
            "job_id": job_id,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "status": "queued_for_indexing",
            "embeddings_created": 0,
        }
    except Exception as exc:
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
    # Placeholder: Qdrant indexing will be implemented in Phase 3.
    # Future work will integrate Qdrant client and collection management.
    return {
        "job_id": job_id,
        "document_id": document_id,
        "tenant_id": tenant_id,
        "status": "completed",
        "vectors_indexed": 0,
    }
