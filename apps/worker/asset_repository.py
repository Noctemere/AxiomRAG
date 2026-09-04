from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import DocumentAssetModel
from packages.contracts.models import DocumentAsset


class AssetRepository(Protocol):
    """Persistence boundary for extracted tenant-owned assets."""

    async def replace_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        assets: list[DocumentAsset],
    ) -> None:
        """Replace all asset metadata for a document atomically."""
        ...


class PostgresAssetRepository:
    """PostgreSQL implementation for extracted asset metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        assets: list[DocumentAsset],
    ) -> None:
        """Delete old metadata and insert the current asset set in one transaction."""
        await self._session.execute(
            delete(DocumentAssetModel).where(
                DocumentAssetModel.document_id == document_id,
                DocumentAssetModel.tenant_id == tenant_id,
            )
        )
        self._session.add_all(
            [
                DocumentAssetModel(
                    asset_id=asset.asset_id,
                    document_id=asset.document_id,
                    tenant_id=asset.tenant_id,
                    modality=asset.modality.value,
                    storage_key=asset.storage_key,
                    page_number=asset.provenance.page_number,
                    region_id=asset.provenance.region_id,
                    created_at=asset.created_at,
                )
                for asset in assets
            ]
        )
        await self._session.commit()