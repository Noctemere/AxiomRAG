from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Modality(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


class Provenance(BaseModel):
    document_id: UUID
    page_number: int | None = Field(default=None, ge=1)
    region_id: str | None = None
    chunk_id: UUID | None = None


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
