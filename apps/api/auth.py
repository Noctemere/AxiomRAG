from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, status

from apps.api.config import get_settings


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request identity used for tenant and audit boundaries."""

    tenant_id: UUID
    actor_id: UUID
    roles: frozenset[str] = frozenset()


class AuthorizationError(PermissionError):
    """Raised when an authenticated actor lacks a required role."""


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
        raw_roles: Any = claims.get("roles", [])
        raw_role_values: list[Any] = (
            raw_roles if isinstance(raw_roles, list) else str(claims.get("scope", "")).split()
        )
        return AuthContext(
            tenant_id=UUID(str(claims["tenant_id"])),
            actor_id=UUID(str(claims["sub"])),
            roles=frozenset(str(role) for role in raw_role_values),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("JWT identity claims are invalid") from exc


def decode_jwks_access_token(
    token: str,
    *,
    jwks_url: str,
    issuer: str,
    audience: str,
) -> AuthContext:
    """Verify an RS256 token using the identity provider's JWKS endpoint."""
    if not jwks_url or not issuer or not audience:
        raise ValueError("JWKS URL, issuer, and audience are required")
    client = jwt.PyJWKClient(jwks_url)
    signing_key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=audience,
        options={"require": ["sub", "tenant_id"]},
    )
    try:
        raw_roles: Any = claims.get("roles", [])
        raw_role_values: list[Any] = (
            raw_roles if isinstance(raw_roles, list) else str(claims.get("scope", "")).split()
        )
        return AuthContext(
            tenant_id=UUID(str(claims["tenant_id"])),
            actor_id=UUID(str(claims["sub"])),
            roles=frozenset(str(role) for role in raw_role_values),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("JWKS identity claims are invalid") from exc


async def get_auth_context(
    x_tenant_id: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> AuthContext:
    """Verify JWT identity in production and use UUID headers only in local mode."""
    settings = get_settings()
    if settings.auth_mode in {"jwt", "jwks"}:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
            )
        try:
            token = authorization.removeprefix("Bearer ").strip()
            if settings.auth_mode == "jwks":
                return decode_jwks_access_token(
                    token,
                    jwks_url=settings.jwt_jwks_url or "",
                    issuer=settings.jwt_issuer or "",
                    audience=settings.jwt_audience or "",
                )
            return decode_access_token(
                token,
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
        roles_value = x_roles if isinstance(x_roles, str) else ""
        roles = frozenset(role.strip() for role in roles_value.split(",") if role.strip())
        return AuthContext(tenant_id=UUID(x_tenant_id), actor_id=UUID(x_actor_id), roles=roles)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="identity headers must contain valid UUIDs",
        ) from exc


def require_roles(context: AuthContext, *required_roles: str) -> AuthContext:
    """Return the context only when the actor has every required role."""
    missing = set(required_roles) - context.roles
    if missing:
        raise AuthorizationError(f"missing required role: {sorted(missing)[0]}")
    return context
