from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class DocumentModel(Base):
    """ORM representation of an uploaded document."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("tenant_id", "sha256"),)

    document_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestionJobModel(Base):
    """ORM representation of an asynchronous ingestion job."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ingestion_jobs_tenant_status_idx", "tenant_id", "status"),
        Index("ingestion_jobs_document_created_idx", "document_id", "created_at"),
    )

    job_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentChunkModel(Base):
    """ORM representation of a normalized searchable document chunk."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("document_chunks_tenant_document_idx", "tenant_id", "document_id"),
        Index("document_chunks_document_page_idx", "document_id", "page_number"),
    )

    chunk_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    region_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentAssetModel(Base):
    """ORM representation of an extracted binary document asset."""

    __tablename__ = "document_assets"
    __table_args__ = (
        Index("document_assets_tenant_document_idx", "tenant_id", "document_id"),
        Index("document_assets_document_page_idx", "document_id", "page_number"),
    )

    asset_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    region_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEventModel(Base):
    """ORM representation of an orchestration security audit event."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("audit_events_tenant_created_idx", "tenant_id", "created_at"),
        Index("audit_events_actor_created_idx", "actor_id", "created_at"),
    )

    event_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed: Mapped[bool] = mapped_column(nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantMembershipModel(Base):
    """ORM representation of an actor's tenant membership and roles."""

    __tablename__ = "tenant_memberships"

    tenant_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
