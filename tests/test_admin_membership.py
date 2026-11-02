from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.auth import AuthContext
from apps.api.routes.admin import require_same_tenant


def test_admin_must_manage_same_tenant() -> None:
    """Verify tenant administrators cannot cross tenant boundaries."""
    tenant_id = uuid4()
    with pytest.raises(HTTPException) as error:
        require_same_tenant(
            AuthContext(tenant_id=uuid4(), actor_id=uuid4(), roles=frozenset({"admin"})),
            tenant_id,
        )
    assert error.value.status_code == 403