from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import DocumentChunkModel
from packages.contracts.models import DocumentChunk


class ChunkRepository(Protocol):
    """Persistence boundary for normalized, tenant-scoped document chunks."""

    async def replace_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        chunks: list[DocumentChunk],
    ) -> None:
        """Replace all chunks for a document atomically."""
        ...


class PostgresChunkRepository:
    """PostgreSQL implementation for chunk replacement during reprocessing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        chunks: list[DocumentChunk],
    ) -> None:
        """Delete old chunks and insert the current parse result in one transaction."""
        await self._session.execute(
            delete(DocumentChunkModel).where(
                DocumentChunkModel.document_id == document_id,
                DocumentChunkModel.tenant_id == tenant_id,
            )
        )
        self._session.add_all(
            [
                DocumentChunkModel(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    tenant_id=chunk.tenant_id,
                    content=chunk.content,
                    modality=chunk.modality.value,
                    page_number=chunk.provenance.page_number,
                    region_id=chunk.provenance.region_id,
                    created_at=chunk.created_at,
                )
                for chunk in chunks
            ]
        )
        await self._session.commit()
