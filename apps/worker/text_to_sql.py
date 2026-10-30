from __future__ import annotations

from typing import Protocol

from apps.worker.sql_execution import SafeSqlExecutor
from packages.contracts.models import Query


class SqlGenerator(Protocol):
    """Port for an LLM or deterministic model that proposes SQL."""

    async def generate_sql(self, query: Query) -> str:
        """Generate a candidate query that must still pass policy validation."""
        ...


class SafeTextToSqlExecutor:
    """Connect a SQL generator to the validated execution boundary."""

    def __init__(self, generator: SqlGenerator, executor: SafeSqlExecutor) -> None:
        self._generator = generator
        self._executor = executor

    async def execute(self, query: Query) -> list[dict[str, object]]:
        """Generate SQL and execute it only after AST/policy validation."""
        sql = await self._generator.generate_sql(query)
        return await self._executor.execute_sql(sql)
