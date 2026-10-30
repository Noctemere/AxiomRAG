from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import AuditEventModel
from apps.worker.tool_security import AuditEvent


class PostgresAuditSink:
    """Persist orchestration security events in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(self, event: AuditEvent) -> None:
        """Insert one audit event and commit it independently."""
        self._session.add(
            AuditEventModel(
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                actor_id=event.actor_id,
                tool_name=event.tool_name,
                action=event.action,
                allowed=event.allowed,
                reason=event.reason,
                approval_id=event.approval_id,
                created_at=event.created_at,
            )
        )
        await self._session.commit()