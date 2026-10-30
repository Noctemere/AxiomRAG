import pytest

from apps.worker.sql_execution import SqlSafetyPolicy
from apps.worker.text_to_sql import SafeTextToSqlExecutor
from packages.contracts.models import Query


class FakeGenerator:
    async def generate_sql(self, query: Query) -> str:
        return "SELECT 1"


class FakeExecutor:
    def __init__(self) -> None:
        self.sql = None

    async def execute_sql(self, sql: str) -> list[dict[str, object]]:
        self.sql = sql
        return [{"value": 1}]


@pytest.mark.asyncio
async def test_text_to_sql_uses_validated_executor_port() -> None:
    """Verify SQL generation never bypasses the executor boundary."""
    executor = FakeExecutor()
    result = await SafeTextToSqlExecutor(FakeGenerator(), executor).execute(None)  # type: ignore[arg-type]
    assert result == [{"value": 1}]
    assert executor.sql == "SELECT 1"


def test_policy_is_explicitly_required_for_real_execution() -> None:
    """Verify the production executor requires a configured table allowlist."""
    with pytest.raises(ValueError, match="allowed table"):
        SqlSafetyPolicy(allowed_tables=frozenset())