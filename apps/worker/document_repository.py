from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import DocumentModel
from packages.contracts.models import DocumentRecord


class DocumentRepository(Protocol):
    """Persistence boundary for tenant-owned document metadata."""

    async def create(self, document: DocumentRecord) -> None:
        """Persist a document record."""
        ...

    async def get(self, *, document_id: UUID, tenant_id: UUID) -> DocumentRecord | None:
        """Return a document only when it belongs to the requested tenant."""
        ...


class PostgresDocumentRepository:
    """PostgreSQL implementation of document metadata persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, document: DocumentRecord) -> None:
        """Insert document metadata and commit the transaction."""
        self._session.add(
            DocumentModel(
                document_id=document.document_id,
                tenant_id=document.tenant_id,
                filename=document.metadata.filename,
                content_type=document.metadata.content_type,
                size_bytes=document.metadata.size_bytes,
                sha256=document.metadata.sha256,
                storage_key=document.storage_key,
                created_at=document.created_at,
            )
        )
        await self._session.commit()
