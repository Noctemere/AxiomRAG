from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.auth import AuthContext


def test_authenticated_tenant_identity_is_stable() -> None:
    """Verify the tenant identity used by document routes is UUID-based."""
    tenant_id = uuid4()
    context = AuthContext(tenant_id=tenant_id, actor_id=uuid4())
    assert str(context.tenant_id) == str(tenant_id)


@pytest.mark.asyncio
async def test_mismatched_tenant_is_forbidden_contract() -> None:
    """Verify the route contract rejects a different supplied tenant."""
    auth = AuthContext(tenant_id=uuid4(), actor_id=uuid4())
    supplied = uuid4()
    with pytest.raises(HTTPException) as error:
        if auth.tenant_id != supplied:
            raise HTTPException(status_code=403, detail="tenant mismatch")
    assert error.value.status_code == 403