from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True)
class TraceContext:
    """Correlation metadata shared by a query graph execution."""

    trace_id: UUID
    tenant_id: UUID
    query: str
    started_at: datetime


@dataclass(frozen=True)
class TraceEvent:
    """Redacted lifecycle event suitable for Langfuse or another trace sink."""

    trace_id: UUID
    name: str
    status: str
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TraceSink(Protocol):
    async def record(self, event: TraceEvent) -> None:
        """Persist or forward one trace event."""
        ...


class InMemoryTraceSink:
    """Deterministic trace sink for tests and local development."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def record(self, event: TraceEvent) -> None:
        """Append one trace event without storing query content or secrets."""
        self.events.append(event)


def start_trace(query: str, tenant_id: UUID) -> TraceContext:
    """Create a correlation context while avoiding raw query logging."""
    return TraceContext(
        trace_id=uuid4(),
        tenant_id=tenant_id,
        query="<redacted>",
        started_at=datetime.now(UTC),
    )
