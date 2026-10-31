from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from apps.api.auth import AuthContext, AuthorizationError
from apps.api.database import DatabaseSession
from apps.api.membership_repository import PostgresMembershipRepository


class MembershipRepository(Protocol):
    async def get_roles(self, *, tenant_id: UUID, actor_id: UUID) -> frozenset[str] | None:
        """Return active membership roles or None when no membership exists."""
        ...


@dataclass(frozen=True)
class TenantAccessService:
    """Authorize authenticated actors against tenant membership records."""

    repository: MembershipRepository

    async def authorize(
        self,
        context: AuthContext,
        *,
        required_roles: frozenset[str] = frozenset(),
    ) -> AuthContext:
        """Require active tenant membership and all requested roles."""
        roles = await self.repository.get_roles(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        )
        if roles is None:
            raise AuthorizationError("actor is not an active tenant member")
        missing = required_roles - roles
        if missing:
            raise AuthorizationError(f"missing tenant role: {sorted(missing)[0]}")
        return AuthContext(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            roles=roles,
        )


class InMemoryMembershipRepository:
    """Deterministic membership repository for tests and local development."""

    def __init__(self) -> None:
        self._memberships: dict[tuple[UUID, UUID], frozenset[str]] = {}

    def add(self, *, tenant_id: UUID, actor_id: UUID, roles: frozenset[str]) -> None:
        """Add or replace an active local membership."""
        self._memberships[(tenant_id, actor_id)] = roles

    async def get_roles(self, *, tenant_id: UUID, actor_id: UUID) -> frozenset[str] | None:
        """Return roles for the exact tenant and actor pair."""
        return self._memberships.get((tenant_id, actor_id))


async def require_tenant_membership(
    context: AuthContext,
    session: DatabaseSession,
    *,
    required_roles: frozenset[str] = frozenset(),
) -> AuthContext:
    """Authorize request identity against the PostgreSQL membership table."""
    return await TenantAccessService(PostgresMembershipRepository(session)).authorize(
        context,
        required_roles=required_roles,
    )