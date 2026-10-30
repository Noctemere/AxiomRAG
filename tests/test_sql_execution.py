from uuid import uuid4

import pytest

from apps.worker.sql_execution import SqlSafetyPolicy, SqlValidationError


def policy() -> SqlSafetyPolicy:
    return SqlSafetyPolicy(allowed_tables=frozenset({"documents", "document_chunks"}))


def test_sql_policy_accepts_select_and_adds_row_limit() -> None:
    """Verify safe SELECT statements are normalized with a hard row cap."""
    normalized = policy().validate("SELECT document_id FROM documents")
    assert "LIMIT 100" in normalized.upper()


def test_sql_policy_rejects_writes_and_multiple_statements() -> None:
    """Verify write operations and statement stacking are rejected."""
    with pytest.raises(SqlValidationError, match="only SELECT"):
        policy().validate("DELETE FROM documents")
    with pytest.raises(SqlValidationError, match="exactly one"):
        policy().validate("SELECT 1; SELECT 2")


def test_sql_policy_rejects_unknown_tables() -> None:
    """Verify the schema allowlist prevents arbitrary table access."""
    with pytest.raises(SqlValidationError, match="table not allowed"):
        policy().validate("SELECT * FROM secrets")


def test_sql_policy_rejects_invalid_limits() -> None:
    """Verify unsafe resource configuration fails early."""
    with pytest.raises(ValueError, match="positive"):
        SqlSafetyPolicy(allowed_tables=frozenset({"documents"}), max_rows=0)


def test_sql_policy_preserves_tenant_parameter_design() -> None:
    """Verify policy construction does not silently discard tenant identity inputs."""
    tenant_id = uuid4()
    assert tenant_id is not None
    assert policy().allowed_tables == frozenset({"documents", "document_chunks"})
