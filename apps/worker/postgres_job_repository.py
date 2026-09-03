from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import IngestionJobModel
from packages.contracts.models import IngestionJob, IngestionJobStatus


class PostgresIngestionJobRepository:
    """PostgreSQL implementation of the ingestion job persistence boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job: IngestionJob) -> None:
        """Insert a new job and commit it as part of the current request."""
        now = job.created_at
        self._session.add(
            IngestionJobModel(
                job_id=job.job_id,
                document_id=job.document_id,
                tenant_id=job.tenant_id,
                status=job.status.value,
                error=job.error,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.commit()

    async def update_status(
        self,
        *,
        job_id: UUID,
        tenant_id: UUID,
        status: IngestionJobStatus,
        error: str | None = None,
    ) -> IngestionJob:
        """Update a tenant-owned job and return its current contract representation."""
        result = await self._session.execute(
            select(IngestionJobModel).where(
                IngestionJobModel.job_id == job_id,
                IngestionJobModel.tenant_id == tenant_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise KeyError(f"ingestion job not found: {job_id}")
        model.status = status.value
        model.error = error
        model.updated_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_contract(model)

    async def get_latest_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> IngestionJob | None:
        """Return the latest job only when it belongs to the requested tenant."""
        result = await self._session.execute(
            select(IngestionJobModel)
            .where(
                IngestionJobModel.document_id == document_id,
                IngestionJobModel.tenant_id == tenant_id,
            )
            .order_by(IngestionJobModel.created_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return self._to_contract(model) if model is not None else None

    @staticmethod
    def _to_contract(model: IngestionJobModel) -> IngestionJob:
        """Convert a database row into the public typed job contract."""
        return IngestionJob(
            job_id=model.job_id,
            document_id=model.document_id,
            tenant_id=model.tenant_id,
            status=IngestionJobStatus(model.status),
            error=model.error,
            created_at=model.created_at,
        )
