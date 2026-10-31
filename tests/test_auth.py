from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.auth import get_auth_context


@pytest.mark.asyncio
async def test_auth_context_parses_identity_headers() -> None:
    """Verify valid tenant and actor headers create an auth context."""
    tenant_id, actor_id = uuid4(), uuid4()
    context = await get_auth_context(str(tenant_id), str(actor_id))
    assert context.tenant_id == tenant_id
    assert context.actor_id == actor_id


@pytest.mark.asyncio
async def test_auth_context_rejects_missing_headers() -> None:
    """Verify requests without identity cannot reach orchestration."""
    with pytest.raises(HTTPException) as error:
        await get_auth_context(None, None)
    assert error.value.status_code == 401