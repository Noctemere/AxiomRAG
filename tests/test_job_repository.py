from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from apps.worker.job_repository import InMemoryIngestionJobRepository
from packages.contracts.models import IngestionJob, IngestionJobStatus


def make_job(
    *,
    tenant_id: UUID | None = None,
    created_at: datetime | None = None,
) -> IngestionJob:
    """Build a small valid job contract for repository tests."""
    return IngestionJob(
        job_id=uuid4(),
        document_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        status=IngestionJobStatus.QUEUED,
        created_at=created_at or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_repository_creates_and_updates_job() -> None:
    """Verify job lifecycle persistence."""
    repository = InMemoryIngestionJobRepository()
    job = make_job()
    await repository.create(job)

    updated = await repository.update_status(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        status=IngestionJobStatus.COMPLETED,
    )

    assert updated.status is IngestionJobStatus.COMPLETED
    assert await repository.get_latest_for_document(
        document_id=job.document_id, tenant_id=job.tenant_id
    ) == updated


@pytest.mark.asyncio
async def test_repository_enforces_tenant_scope() -> None:
    """Verify another tenant cannot read or update a job."""
    repository = InMemoryIngestionJobRepository()
    job = make_job()
    other_tenant = uuid4()
    await repository.create(job)

    assert await repository.get_latest_for_document(
        document_id=job.document_id, tenant_id=other_tenant
    ) is None
    with pytest.raises(KeyError):
        await repository.update_status(
            job_id=job.job_id,
            tenant_id=other_tenant,
            status=IngestionJobStatus.FAILED,
        )


@pytest.mark.asyncio
async def test_repository_returns_latest_job() -> None:
    """Verify reprocessing returns the newest job for a document."""
    repository = InMemoryIngestionJobRepository()
    tenant_id = uuid4()
    document_id = uuid4()
    first = make_job(tenant_id=tenant_id, created_at=datetime.now(UTC))
    first = first.model_copy(update={"document_id": document_id})
    second = make_job(
        tenant_id=tenant_id,
        created_at=first.created_at + timedelta(seconds=1),
    )
    second = second.model_copy(update={"document_id": document_id})
    await repository.create(first)
    await repository.create(second)

    latest = await repository.get_latest_for_document(
        document_id=document_id, tenant_id=tenant_id
    )
    assert latest is not None
    assert latest.job_id == second.job_id
