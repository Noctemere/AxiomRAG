from __future__ import annotations

from datetime import UTC, datetime
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

    async def upsert_membership(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        roles: frozenset[str],
    ) -> None:
        """Create or reactivate a tenant membership with the requested roles."""
        result = await self._session.execute(
            select(TenantMembershipModel).where(
                TenantMembershipModel.tenant_id == tenant_id,
                TenantMembershipModel.actor_id == actor_id,
            )
        )
        membership = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if membership is None:
            self._session.add(
                TenantMembershipModel(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    roles=sorted(roles),
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            membership.roles = sorted(roles)
            membership.active = True
            membership.updated_at = now
        await self._session.commit()

    async def deactivate_membership(self, *, tenant_id: UUID, actor_id: UUID) -> None:
        """Deactivate a membership without deleting its audit history."""
        result = await self._session.execute(
            select(TenantMembershipModel).where(
                TenantMembershipModel.tenant_id == tenant_id,
                TenantMembershipModel.actor_id == actor_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is not None:
            membership.active = False
            membership.updated_at = datetime.now(UTC)
            await self._session.commit()
