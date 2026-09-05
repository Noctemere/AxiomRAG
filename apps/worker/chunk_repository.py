from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import DocumentChunkModel
from packages.contracts.models import DocumentChunk, Modality, Provenance


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

    async def list_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> list[DocumentChunk]:
        """Return chunks visible to the requested tenant."""
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

    async def list_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> list[DocumentChunk]:
        """Load chunks for embedding while preserving tenant isolation."""
        from sqlalchemy import select

        result = await self._session.execute(
            select(DocumentChunkModel)
            .where(
                DocumentChunkModel.document_id == document_id,
                DocumentChunkModel.tenant_id == tenant_id,
            )
            .order_by(DocumentChunkModel.created_at, DocumentChunkModel.chunk_id)
        )
        return [
            DocumentChunk(
                chunk_id=model.chunk_id,
                document_id=model.document_id,
                tenant_id=model.tenant_id,
                content=model.content,
                modality=Modality(model.modality),
                provenance=Provenance(
                    document_id=model.document_id,
                    page_number=model.page_number,
                    region_id=model.region_id,
                    chunk_id=model.chunk_id,
                ),
                created_at=model.created_at,
            )
            for model in result.scalars()
        ]
