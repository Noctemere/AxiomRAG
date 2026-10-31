from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from apps.api.auth import decode_access_token, get_auth_context


def test_decode_access_token_extracts_identity_claims() -> None:
    """Verify signed JWT claims become tenant and actor identity."""
    tenant_id, actor_id = uuid4(), uuid4()
    token = jwt.encode(
        {"sub": str(actor_id), "tenant_id": str(tenant_id)},
        "test-secret",
        algorithm="HS256",
    )
    context = decode_access_token(token, secret="test-secret")
    assert context.tenant_id == tenant_id
    assert context.actor_id == actor_id


def test_decode_access_token_rejects_wrong_secret() -> None:
    """Verify invalid signatures are rejected."""
    token = jwt.encode(
        {"sub": str(uuid4()), "tenant_id": str(uuid4())},
        "secret",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, secret="wrong")


@pytest.mark.asyncio
async def test_local_auth_still_accepts_development_headers() -> None:
    """Verify local mode preserves the development workflow."""
    tenant_id, actor_id = uuid4(), uuid4()
    context = await get_auth_context(str(tenant_id), str(actor_id))
    assert context.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_local_auth_rejects_missing_identity() -> None:
    """Verify local requests still require both identity headers."""
    with pytest.raises(HTTPException) as error:
        await get_auth_context(None, None, None)
    assert error.value.status_code == 401
