from typing import Any
from uuid import uuid4

import pytest

from apps.api.membership_repository import PostgresMembershipRepository


class FakeResult:
    def __init__(self, roles: list[str] | None):
        self.roles = roles

    def scalar_one_or_none(self):
        return self.roles


class FakeSession:
    def __init__(self, roles: list[str] | None):
        self.roles = roles

    async def execute(self, statement: Any) -> FakeResult:
        return FakeResult(self.roles)


@pytest.mark.asyncio
async def test_postgres_repository_maps_roles() -> None:
    """Verify the database repository converts role arrays to a set."""
    repository = PostgresMembershipRepository(FakeSession(["reader", "admin"]))  # type: ignore[arg-type]
    roles = await repository.get_roles(tenant_id=uuid4(), actor_id=uuid4())
    assert roles == frozenset({"reader", "admin"})


@pytest.mark.asyncio
async def test_postgres_repository_returns_none_without_membership() -> None:
    """Verify missing membership remains a deny-by-default result."""
    repository = PostgresMembershipRepository(FakeSession(None))  # type: ignore[arg-type]
    roles = await repository.get_roles(tenant_id=uuid4(), actor_id=uuid4())
    assert roles is None