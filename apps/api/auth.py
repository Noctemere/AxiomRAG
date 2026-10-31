from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request identity used for tenant and audit boundaries."""

    tenant_id: UUID
    actor_id: UUID


async def get_auth_context(
    x_tenant_id: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
) -> AuthContext:
    """Parse development identity headers; replace with JWT/OIDC verification in production."""
    if not x_tenant_id or not x_actor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-ID and X-Actor-ID headers are required",
        )
    try:
        return AuthContext(tenant_id=UUID(x_tenant_id), actor_id=UUID(x_actor_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="identity headers must contain valid UUIDs",
        ) from exc
