from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, status

from apps.api.config import get_settings


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request identity used for tenant and audit boundaries."""

    tenant_id: UUID
    actor_id: UUID


def decode_access_token(
    token: str,
    *,
    secret: str,
    issuer: str | None = None,
    audience: str | None = None,
) -> AuthContext:
    """Verify an HS256 access token and extract tenant and actor claims."""
    if not secret:
        raise ValueError("JWT secret is not configured")
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=issuer,
        audience=audience,
        options={"require": ["sub", "tenant_id"]},
    )
    try:
        return AuthContext(
            tenant_id=UUID(str(claims["tenant_id"])),
            actor_id=UUID(str(claims["sub"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("JWT identity claims are invalid") from exc


async def get_auth_context(
    x_tenant_id: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """Verify JWT identity in production and use UUID headers only in local mode."""
    settings = get_settings()
    if settings.auth_mode == "jwt":
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
            )
        try:
            return decode_access_token(
                authorization.removeprefix("Bearer ").strip(),
                secret=settings.jwt_secret or "",
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
            )
        except (ValueError, jwt.PyJWTError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid access token",
            ) from exc
    if not x_tenant_id or not x_actor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-ID and X-Actor-ID headers are required in local mode",
        )
    try:
        return AuthContext(tenant_id=UUID(x_tenant_id), actor_id=UUID(x_actor_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="identity headers must contain valid UUIDs",
        ) from exc
