from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.auth import AuthContext, require_roles
from apps.api.database import DatabaseSession
from apps.api.membership import get_authorized_context
from apps.api.membership_repository import PostgresMembershipRepository


class MembershipRequest(BaseModel):
    actor_id: UUID
    roles: frozenset[str] = Field(default_factory=frozenset)


router = APIRouter(prefix="/api/v1/admin/tenants", tags=["admin"])


def require_same_tenant(auth: AuthContext, tenant_id: UUID) -> AuthContext:
    """Require an administrator to manage only their authenticated tenant."""
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant access denied")
    return require_roles(auth, "admin")


@router.put("/{tenant_id}/memberships", status_code=status.HTTP_204_NO_CONTENT)
async def upsert_membership(
    tenant_id: UUID,
    request: MembershipRequest,
    session: DatabaseSession,
    auth: AuthContext = Depends(get_authorized_context),  # noqa: B008
) -> None:
    """Create or reactivate a tenant membership for an administrator's tenant."""
    require_same_tenant(auth, tenant_id)
    await PostgresMembershipRepository(session).upsert_membership(
        tenant_id=tenant_id,
        actor_id=request.actor_id,
        roles=request.roles,
    )


@router.delete("/{tenant_id}/memberships/{actor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_membership(
    tenant_id: UUID,
    actor_id: UUID,
    session: DatabaseSession,
    auth: AuthContext = Depends(get_authorized_context),  # noqa: B008
) -> None:
    """Deactivate a tenant membership for an administrator's tenant."""
    require_same_tenant(auth, tenant_id)
    await PostgresMembershipRepository(session).deactivate_membership(
        tenant_id=tenant_id,
        actor_id=actor_id,
    )