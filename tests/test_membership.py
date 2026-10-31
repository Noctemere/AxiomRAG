from uuid import uuid4

import pytest

from apps.api.auth import AuthContext, AuthorizationError
from apps.api.membership import InMemoryMembershipRepository, TenantAccessService


@pytest.mark.asyncio
async def test_membership_authorizes_roles_for_exact_tenant() -> None:
    """Verify active membership and requested roles are required."""
    tenant_id, actor_id = uuid4(), uuid4()
    repository = InMemoryMembershipRepository()
    repository.add(tenant_id=tenant_id, actor_id=actor_id, roles=frozenset({"reader"}))

    context = await TenantAccessService(repository).authorize(
        AuthContext(tenant_id, actor_id),
        required_roles=frozenset({"reader"}),
    )

    assert context.roles == frozenset({"reader"})


@pytest.mark.asyncio
async def test_membership_rejects_wrong_tenant_or_role() -> None:
    """Verify membership does not leak across tenants or roles."""
    tenant_id, actor_id = uuid4(), uuid4()
    repository = InMemoryMembershipRepository()
    repository.add(tenant_id=tenant_id, actor_id=actor_id, roles=frozenset({"reader"}))
    service = TenantAccessService(repository)

    with pytest.raises(AuthorizationError, match="not an active"):
        await service.authorize(AuthContext(uuid4(), actor_id))
    with pytest.raises(AuthorizationError, match="missing tenant role"):
        await service.authorize(
            AuthContext(tenant_id, actor_id),
            required_roles=frozenset({"admin"}),
        )