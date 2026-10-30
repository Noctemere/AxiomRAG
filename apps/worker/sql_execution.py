from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import sqlglot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

from packages.contracts.models import Query


class SqlValidationError(ValueError):
    """Raised when generated SQL violates the read-only execution policy."""


class SqlQueryGenerator(Protocol):
    async def generate_sql(self, query: Query) -> str:
        """Generate SQL that will be validated before execution."""
        ...


@dataclass(frozen=True)
class SqlSafetyPolicy:
    """Allowlist and resource policy for model-generated SQL."""

    allowed_tables: frozenset[str]
    max_rows: int = 100
    timeout_seconds: float = 5.0
    dialect: str = "postgres"

    def __post_init__(self) -> None:
        if not self.allowed_tables:
            raise ValueError("at least one allowed table is required")
        if self.max_rows < 1 or self.timeout_seconds <= 0:
            raise ValueError("SQL resource limits must be positive")

    def validate(self, sql: str) -> str:
        """Parse and validate one read-only SELECT statement, returning normalized SQL."""
        if not sql.strip():
            raise SqlValidationError("SQL query is empty")
        try:
            statements = sqlglot.parse(sql, read=self.dialect)
        except ParseError as exc:
            raise SqlValidationError("SQL query could not be parsed") from exc
        if len(statements) != 1:
            raise SqlValidationError("exactly one SQL statement is required")
        statement = statements[0]
        if not isinstance(statement, exp.Select):
            raise SqlValidationError("only SELECT statements are permitted")
        tables = {table.name for table in statement.find_all(exp.Table)}
        unknown_tables = tables - self.allowed_tables
        if unknown_tables:
            raise SqlValidationError(f"table not allowed: {sorted(unknown_tables)[0]}")
        if any(
            statement.find(kind) for kind in (exp.Insert, exp.Update, exp.Delete)
        ):
            raise SqlValidationError("write operations are not permitted")
        limited = statement.limit(self.max_rows)
        return limited.sql(dialect=self.dialect)


class SafeSqlExecutor:
    """Execute validated read-only SQL with tenant context and resource limits."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        policy: SqlSafetyPolicy,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy

    async def execute_sql(self, sql: str) -> list[dict[str, object]]:
        """Validate, execute with a timeout, and return bounded mapping rows."""
        normalized_sql = self._policy.validate(sql)
        async with self._session_factory() as session:
            result = await asyncio.wait_for(
                session.execute(text(normalized_sql)),
                timeout=self._policy.timeout_seconds,
            )
            return [dict(row) for row in result.mappings().all()]


class QuerySqlExecutor:
    """Adapt a SQL generator to the orchestration graph's executor port."""

    def __init__(self, generator: SqlQueryGenerator, executor: SafeSqlExecutor) -> None:
        self._generator = generator
        self._executor = executor

    async def execute(self, query: Query) -> list[dict[str, object]]:
        """Generate SQL, then force it through the safety policy before execution."""
        sql = await self._generator.generate_sql(query)
        return await self._executor.execute_sql(sql)
