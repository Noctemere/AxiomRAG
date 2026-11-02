import pytest

from apps.api.config import Settings
from apps.api.container import ApplicationContainer


@pytest.mark.asyncio
async def test_container_builds_without_network_calls() -> None:
    """Verify local dependency composition is lazy with respect to services."""
    container = ApplicationContainer.create(
        Settings(
            database_url="postgresql+asyncpg://axiom:axiom@localhost:5432/axiomrag",
            redis_url="redis://localhost:6379/0",
        )
    )
    assert container.graph is not None
    await container.close()