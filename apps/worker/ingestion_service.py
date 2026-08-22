from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from apps.worker.storage import DocumentStore, content_sha256
from packages.contracts.models import (
    DocumentMetadata,
    DocumentRecord,
    IngestionJob,
    IngestionJobStatus,
)


class IngestionValidationError(ValueError):
    """Raised when an uploaded document violates ingestion limits or policy."""


class IngestionService:
    """Validates and persists an upload before asynchronous parsing begins."""

    def __init__(
        self,
        document_store: DocumentStore,
        allowed_content_types: frozenset[str],
        max_size_bytes: int,
    ) -> None:
        if max_size_bytes < 1:
            raise ValueError("max_size_bytes must be positive")
        if not allowed_content_types:
            raise ValueError("at least one content type is required")
        self._document_store = document_store
        self._allowed_content_types = allowed_content_types
        self._max_size_bytes = max_size_bytes

    async def accept_upload(
        self,
        *,
        tenant_id: UUID,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> tuple[DocumentRecord, IngestionJob]:
        """Validate an upload, persist it, and return records for job dispatch."""
        self._validate_upload(filename, content_type, content)
        document_id = uuid4()
        job_id = uuid4()
        metadata = DocumentMetadata(
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256=content_sha256(content),
        )
        storage_key = f"{tenant_id}/{document_id}/{filename}"
        await self._document_store.save(storage_key, content)
        created_at = datetime.now(UTC)
        return (
            DocumentRecord(
                document_id=document_id,
                tenant_id=tenant_id,
                metadata=metadata,
                storage_key=storage_key,
                created_at=created_at,
            ),
            IngestionJob(
                job_id=job_id,
                document_id=document_id,
                tenant_id=tenant_id,
                status=IngestionJobStatus.QUEUED,
                created_at=created_at,
            ),
        )

    def _validate_upload(self, filename: str, content_type: str, content: bytes) -> None:
        if not filename.strip() or filename in {".", ".."}:
            raise IngestionValidationError("filename is required")
        if "/" in filename or "\\" in filename:
            raise IngestionValidationError("filename must not contain path separators")
        if content_type not in self._allowed_content_types:
            raise IngestionValidationError(f"unsupported content type: {content_type}")
        if not content:
            raise IngestionValidationError("document is empty")
        if len(content) > self._max_size_bytes:
            raise IngestionValidationError("document exceeds the configured size limit")