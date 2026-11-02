from typing import Any
from uuid import uuid4

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import HTTPException

from apps.api.auth import AuthContext, AuthorizationError
from apps.api.membership import get_authorized_context


@pytest.mark.asyncio
async def test_local_mode_returns_authenticated_context_without_database() -> None:
    """Verify local development remains usable without PostgreSQL membership rows."""
    context = AuthContext(uuid4(), uuid4(), frozenset())
    result = await get_authorized_context(context, None)  # type: ignore[arg-type]
    assert result is context


@pytest.mark.asyncio
async def test_membership_authorization_maps_denial_to_forbidden(
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify membership failures become HTTP 403 responses."""
    class Settings:
        auth_mode = "jwt"

    async def denied(context: AuthContext, session: Any) -> AuthContext:
        raise AuthorizationError("actor is not an active tenant member")

    monkeypatch.setattr("apps.api.membership.get_settings", lambda: Settings())
    monkeypatch.setattr("apps.api.membership.require_tenant_membership", denied)
    with pytest.raises(HTTPException) as error:
        await get_authorized_context(AuthContext(uuid4(), uuid4()), None)  # type: ignore[arg-type]
    assert error.value.status_code == 403