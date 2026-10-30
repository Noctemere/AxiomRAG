from uuid import uuid4

import pytest

from apps.worker.tool_security import (
    ApprovalRequiredError,
    AuthorizedToolExecutor,
    InMemoryAuditSink,
    ToolPolicy,
)


@pytest.mark.asyncio
async def test_high_risk_tool_requires_approval() -> None:
    """Verify high-risk tools cannot execute without a human approval ID."""
    sink = InMemoryAuditSink()
    executor = AuthorizedToolExecutor(
        ToolPolicy(
            allowed_tools=frozenset({"delete_document"}),
            approval_required_tools=frozenset({"delete_document"}),
        ),
        sink,
    )
    with pytest.raises(ApprovalRequiredError, match="human approval"):
        await executor.execute(
            tenant_id=uuid4(),
            actor_id=uuid4(),
            tool_name="delete_document",
            action="delete",
            arguments={"document_id": "doc"},
        )
    assert sink.events[0].allowed is True
    assert sink.events[0].reason == "human approval is required"


@pytest.mark.asyncio
async def test_high_risk_tool_executes_with_approval() -> None:
    """Verify an explicit approval ID permits and audits a high-risk action."""
    sink = InMemoryAuditSink()
    executor = AuthorizedToolExecutor(
        ToolPolicy(
            allowed_tools=frozenset({"delete_document"}),
            approval_required_tools=frozenset({"delete_document"}),
        ),
        sink,
    )
    approval_id = uuid4()
    result = await executor.execute(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        tool_name="delete_document",
        action="delete",
        arguments={"document_id": "doc"},
        approval_id=approval_id,
    )
    assert result["tool"] == "delete_document"
    assert sink.events[0].approval_id == approval_id