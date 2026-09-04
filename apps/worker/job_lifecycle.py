from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.postgres_job_repository import PostgresIngestionJobRepository
from packages.contracts.models import IngestionJob, IngestionJobStatus


class JobLifecycleService:
    """Coordinates tenant-scoped ingestion job state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = PostgresIngestionJobRepository(session)

    async def create_queued(self, job: IngestionJob) -> None:
        """Persist a newly accepted job in the queued state."""
        await self._repository.create(job)

    async def mark_processing(self, *, job_id: UUID, tenant_id: UUID) -> IngestionJob:
        """Move a job into processing before expensive work begins."""
        return await self._repository.update_status(
            job_id=job_id,
            tenant_id=tenant_id,
            status=IngestionJobStatus.PROCESSING,
        )

    async def mark_completed(self, *, job_id: UUID, tenant_id: UUID) -> IngestionJob:
        """Mark a fully completed ingestion pipeline."""
        return await self._repository.update_status(
            job_id=job_id,
            tenant_id=tenant_id,
            status=IngestionJobStatus.COMPLETED,
        )

    async def mark_failed(
        self,
        *,
        job_id: UUID,
        tenant_id: UUID,
        error: str,
    ) -> IngestionJob:
        """Record a sanitized failure message for a tenant-owned job."""
        return await self._repository.update_status(
            job_id=job_id,
            tenant_id=tenant_id,
            status=IngestionJobStatus.FAILED,
            error=error[:2_000],
        )

    async def latest_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> IngestionJob | None:
        """Return the newest job visible to the requested tenant."""
        return await self._repository.get_latest_for_document(
            document_id=document_id,
            tenant_id=tenant_id,
        )
