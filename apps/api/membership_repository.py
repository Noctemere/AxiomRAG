from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.db_models import TenantMembershipModel


class PostgresMembershipRepository:
    """Load active tenant membership roles from PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_roles(self, *, tenant_id: UUID, actor_id: UUID) -> frozenset[str] | None:
        """Return roles only for an active exact tenant/actor membership."""
        result = await self._session.execute(
            select(TenantMembershipModel.roles).where(
                TenantMembershipModel.tenant_id == tenant_id,
                TenantMembershipModel.actor_id == actor_id,
                TenantMembershipModel.active.is_(True),
            )
        )
        roles = result.scalar_one_or_none()
        return frozenset(roles) if roles is not None else None
