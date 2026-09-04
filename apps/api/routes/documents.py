from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from apps.api.database import SessionFactory
from apps.worker.document_repository import PostgresDocumentRepository
from apps.worker.ingestion_service import (
    IngestionService,
    IngestionValidationError,
)
from apps.worker.job_lifecycle import JobLifecycleService
from apps.worker.storage import LocalDocumentStore
from apps.worker.tasks import (  # type: ignore[attr-defined]
    embed_chunks,
    index_to_qdrant,
    parse_document,
)
from packages.contracts.models import IngestionJob

# Initialize storage and service at module scope for reuse across requests.
_document_store = LocalDocumentStore(Path("data/documents"))
_ingestion_service = IngestionService(
    document_store=_document_store,
    allowed_content_types=frozenset({
        "application/pdf",
        "text/plain",
        "text/markdown",
    }),
    max_size_bytes=100_000_000,  # 100 MB
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=IngestionJob)
async def upload_document(
    tenant_id: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008
) -> IngestionJob:
    """Accept a document upload and dispatch an asynchronous ingestion pipeline.

    The upload is validated immediately for size, type, and path safety.
    The document is persisted synchronously before returning to the client.
    A Celery task chain is dispatched for asynchronous parsing and indexing.

    Args:
        tenant_id: Tenant UUID as a string
        file: The uploaded document file

    Returns:
        The created IngestionJob with status "queued".

    Raises:
        HTTPException 400: Validation error (unsupported type, oversized file, etc.)
        HTTPException 422: Tenant ID is not a valid UUID
        HTTPException 413: File size exceeds the configured limit
        HTTPException 500: Document storage failed
    """
    try:
        tenant_uuid = UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tenant_id must be a valid UUID",
        ) from exc

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename is required",
        )

    try:
        content = await file.read()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to read uploaded file",
        ) from exc

    try:
        document, job = await _ingestion_service.accept_upload(
            tenant_id=tenant_uuid,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except IngestionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to persist document",
        ) from exc

    async with SessionFactory() as session:
        await PostgresDocumentRepository(session).create(document)
        await JobLifecycleService(session).create_queued(job)

    # Dispatch the asynchronous ingestion task chain.
    # The chain ensures tasks run in order: parse -> embed -> index.
    task_chain = (
        parse_document.si(  # type: ignore[attr-defined]
            job_id=str(job.job_id),
            document_id=str(document.document_id),
            tenant_id=str(tenant_uuid),
            storage_key=document.storage_key,
            content_type=document.metadata.content_type,
        )
        | embed_chunks.si(  # type: ignore[attr-defined]
            job_id=str(job.job_id),
            document_id=str(document.document_id),
            tenant_id=str(tenant_uuid),
        )
        | index_to_qdrant.si(  # type: ignore[attr-defined]
            job_id=str(job.job_id),
            document_id=str(document.document_id),
            tenant_id=str(tenant_uuid),
        )
    )
    task_chain.apply_async()  # type: ignore[attr-defined]

    return job


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    tenant_id: str,
) -> dict[str, str]:
    """Retrieve the ingestion status of a document.

    This is a placeholder endpoint. In production, it would:
    1. Verify that the requesting tenant owns the document.
    2. Query the job database to find the latest ingestion job.
    3. Return the current status and any error messages.

    Args:
        document_id: Document UUID as a string
        tenant_id: Tenant UUID as a string

    Returns:
        A dictionary with the current job status.
    """
    try:
        document_uuid = UUID(document_id)
        tenant_uuid = UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_id and tenant_id must be valid UUIDs",
        ) from exc

    async with SessionFactory() as session:
        job = await JobLifecycleService(session).latest_for_document(
            document_id=document_uuid,
            tenant_id=tenant_uuid,
        )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )
    return {"document_id": document_id, "status": job.status.value}
