from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from uuid import uuid4

import pytest

from apps.worker.ingestion_service import (
    IngestionService,
    IngestionValidationError,
)
from apps.worker.storage import LocalDocumentStore, content_sha256


@pytest.fixture
def temp_store() -> Iterator[LocalDocumentStore]:
    """Provide a temporary document store for each test."""
    with TemporaryDirectory() as tmpdir:
        yield LocalDocumentStore(Path(tmpdir))


@pytest.fixture
def ingestion_service(temp_store: LocalDocumentStore) -> IngestionService:
    """Provide a configured ingestion service with conservative size limits."""
    return IngestionService(
        document_store=temp_store,
        allowed_content_types=frozenset({"application/pdf", "text/plain"}),
        max_size_bytes=10_000_000,
    )


@pytest.mark.asyncio
async def test_accept_upload_creates_records(
    ingestion_service: IngestionService,
) -> None:
    """Verify that a valid upload creates both DocumentRecord and IngestionJob."""
    tenant_id = uuid4()
    content = b"Hello, world!"
    filename = "test.txt"

    document, job = await ingestion_service.accept_upload(
        tenant_id=tenant_id,
        filename=filename,
        content_type="text/plain",
        content=content,
    )

    assert document.document_id is not None
    assert document.tenant_id == tenant_id
    assert document.metadata.filename == filename
    assert document.metadata.content_type == "text/plain"
    assert document.metadata.size_bytes == len(content)
    assert document.metadata.sha256 == content_sha256(content)
    assert document.storage_key == f"{tenant_id}/{document.document_id}/{filename}"

    assert job.document_id == document.document_id
    assert job.tenant_id == tenant_id
    assert job.status.value == "queued"
    assert job.error is None


@pytest.mark.asyncio
async def test_accept_upload_persists_content(
    ingestion_service: IngestionService,
    temp_store: LocalDocumentStore,
) -> None:
    """Verify that uploaded content is durably stored."""
    tenant_id = uuid4()
    content = b"Persisted content"

    document, _ = await ingestion_service.accept_upload(
        tenant_id=tenant_id,
        filename="test.txt",
        content_type="text/plain",
        content=content,
    )

    stored_content = await temp_store.read(document.storage_key)
    assert stored_content == content


@pytest.mark.asyncio
async def test_accept_upload_rejects_empty_file(
    ingestion_service: IngestionService,
) -> None:
    """Verify that empty files are rejected."""
    with pytest.raises(IngestionValidationError, match="empty"):
        await ingestion_service.accept_upload(
            tenant_id=uuid4(),
            filename="empty.txt",
            content_type="text/plain",
            content=b"",
        )


@pytest.mark.asyncio
async def test_accept_upload_rejects_unsupported_content_type(
    ingestion_service: IngestionService,
) -> None:
    """Verify that unsupported MIME types are rejected."""
    with pytest.raises(IngestionValidationError, match="unsupported content type"):
        await ingestion_service.accept_upload(
            tenant_id=uuid4(),
            filename="image.png",
            content_type="image/png",
            content=b"fake image data",
        )


@pytest.mark.asyncio
async def test_accept_upload_rejects_oversized_file(
    ingestion_service: IngestionService,
) -> None:
    """Verify that files exceeding the size limit are rejected."""
    max_bytes = 10_000_000  # Matches the fixture configuration
    content = b"x" * (max_bytes + 1)
    with pytest.raises(IngestionValidationError, match="exceeds"):
        await ingestion_service.accept_upload(
            tenant_id=uuid4(),
            filename="large.pdf",
            content_type="application/pdf",
            content=content,
        )


@pytest.mark.asyncio
async def test_accept_upload_rejects_blank_filename(
    ingestion_service: IngestionService,
) -> None:
    """Verify that blank filenames are rejected."""
    with pytest.raises(IngestionValidationError, match="required"):
        await ingestion_service.accept_upload(
            tenant_id=uuid4(),
            filename="   ",
            content_type="text/plain",
            content=b"content",
        )


@pytest.mark.asyncio
async def test_accept_upload_rejects_path_separators_in_filename(
    ingestion_service: IngestionService,
) -> None:
    """Verify that filenames with path separators are rejected."""
    for bad_name in ["../secret.txt", "subfolder/file.txt", "folder\\file.txt"]:
        with pytest.raises(IngestionValidationError, match="path separators"):
            await ingestion_service.accept_upload(
                tenant_id=uuid4(),
                filename=bad_name,
                content_type="text/plain",
                content=b"content",
            )


@pytest.mark.asyncio
async def test_accept_upload_rejects_dot_filenames(
    ingestion_service: IngestionService,
) -> None:
    """Verify that . and .. filenames are rejected."""
    for bad_name in [".", ".."]:
        with pytest.raises(IngestionValidationError, match="required"):
            await ingestion_service.accept_upload(
                tenant_id=uuid4(),
                filename=bad_name,
                content_type="text/plain",
                content=b"content",
            )


@pytest.mark.asyncio
async def test_content_sha256_is_deterministic() -> None:
    """Verify that SHA-256 digests are reproducible."""
    content = b"test content for hashing"
    hash1 = content_sha256(content)
    hash2 = content_sha256(content)
    assert hash1 == hash2
    assert len(hash1) == 64
    assert all(c in "0123456789abcdef" for c in hash1)


@pytest.mark.asyncio
async def test_content_sha256_differs_for_different_content() -> None:
    """Verify that different content produces different digests."""
    hash1 = content_sha256(b"content1")
    hash2 = content_sha256(b"content2")
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_accept_upload_unique_document_ids(
    ingestion_service: IngestionService,
) -> None:
    """Verify that repeated uploads generate unique document IDs."""
    tenant_id = uuid4()

    doc1, _ = await ingestion_service.accept_upload(
        tenant_id=tenant_id,
        filename="test.txt",
        content_type="text/plain",
        content=b"content1",
    )

    doc2, _ = await ingestion_service.accept_upload(
        tenant_id=tenant_id,
        filename="test.txt",
        content_type="text/plain",
        content=b"content2",
    )

    assert doc1.document_id != doc2.document_id


@pytest.mark.asyncio
async def test_storage_key_includes_tenant_isolation(
    ingestion_service: IngestionService,
) -> None:
    """Verify that storage keys are tenant-scoped."""
    tenant1 = uuid4()
    tenant2 = uuid4()

    doc1, _ = await ingestion_service.accept_upload(
        tenant_id=tenant1,
        filename="test.txt",
        content_type="text/plain",
        content=b"content",
    )

    doc2, _ = await ingestion_service.accept_upload(
        tenant_id=tenant2,
        filename="test.txt",
        content_type="text/plain",
        content=b"content",
    )

    assert doc1.storage_key.startswith(str(tenant1))
    assert doc2.storage_key.startswith(str(tenant2))
    assert doc1.storage_key != doc2.storage_key
