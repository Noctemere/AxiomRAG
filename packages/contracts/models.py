from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Modality(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


class IngestionJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class DocumentRecord(BaseModel):
    document_id: UUID
    tenant_id: UUID
    metadata: DocumentMetadata
    storage_key: str = Field(min_length=1)
    created_at: datetime


class IngestionJob(BaseModel):
    job_id: UUID
    document_id: UUID
    tenant_id: UUID
    status: IngestionJobStatus
    error: str | None = None
    created_at: datetime


class Provenance(BaseModel):
    document_id: UUID
    page_number: int | None = Field(default=None, ge=1)
    region_id: str | None = None
    chunk_id: UUID | None = None


class DocumentChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    tenant_id: UUID
    content: str = Field(min_length=1)
    modality: Modality
    provenance: Provenance


class Query(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    conversation_id: UUID | None = None
    tenant_id: UUID


class Citation(BaseModel):
    source_name: str
    quote: str
    provenance: Provenance


class Answer(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=lambda: list[Citation]())
    model: str | None = None
    created_at: datetime


class StreamEventType(StrEnum):
    TOKEN = "token"
    CITATION = "citation"
    COMPLETE = "complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    event_id: str
    event_type: StreamEventType
    data: str
    created_at: datetime
