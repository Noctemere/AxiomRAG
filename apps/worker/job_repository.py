from __future__ import annotations

from typing import Protocol
from uuid import UUID

from packages.contracts.models import IngestionJob, IngestionJobStatus


class IngestionJobRepository(Protocol):
    """Persistence boundary for ingestion job state.

    A PostgreSQL implementation will be added after the async database driver and
    migration runner are introduced. Workers depend on this contract, not SQL.
    """

    async def create(self, job: IngestionJob) -> None:
        """Persist a newly queued ingestion job."""
        ...

    async def update_status(
        self,
        *,
        job_id: UUID,
        tenant_id: UUID,
        status: IngestionJobStatus,
        error: str | None = None,
    ) -> IngestionJob:
        """Atomically update a job owned by the tenant and return its new state."""
        ...

    async def get_latest_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> IngestionJob | None:
        """Return the newest job for a document, scoped to its tenant."""
        ...


class InMemoryIngestionJobRepository:
    """Deterministic repository for unit tests and local development."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, IngestionJob] = {}

    async def create(self, job: IngestionJob) -> None:
        """Store a queued job and reject accidental duplicate IDs."""
        if job.job_id in self._jobs:
            raise ValueError(f"ingestion job already exists: {job.job_id}")
        self._jobs[job.job_id] = job

    async def update_status(
        self,
        *,
        job_id: UUID,
        tenant_id: UUID,
        status: IngestionJobStatus,
        error: str | None = None,
    ) -> IngestionJob:
        """Update status only when the job belongs to the requested tenant."""
        job = self._jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise KeyError(f"ingestion job not found: {job_id}")
        updated = job.model_copy(
            update={"status": status, "error": error[:2_000] if error else None}
        )
        self._jobs[job_id] = updated
        return updated

    async def get_latest_for_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
    ) -> IngestionJob | None:
        """Return the newest tenant-owned job for a document."""
        matches = [
            job
            for job in self._jobs.values()
            if job.document_id == document_id and job.tenant_id == tenant_id
        ]
        return max(matches, key=lambda job: job.created_at) if matches else None
