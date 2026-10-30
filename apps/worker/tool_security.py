from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4


class ToolAuthorizationError(PermissionError):
    """Raised when a caller is not allowed to invoke a tool."""


class PromptInjectionError(ValueError):
    """Raised when untrusted content attempts to control tool execution."""


class ApprovalRequiredError(PermissionError):
    """Raised when a high-risk tool needs explicit human approval."""


@dataclass(frozen=True)
class AuditEvent:
    """Structured record for an authorized or rejected tool action."""

    event_id: UUID
    tenant_id: UUID
    actor_id: UUID
    tool_name: str
    action: str
    allowed: bool
    reason: str | None
    approval_id: UUID | None
    created_at: datetime


class AuditSink(Protocol):
    async def write(self, event: AuditEvent) -> None:
        """Persist or forward an audit event."""
        ...


class InMemoryAuditSink:
    """Deterministic audit sink for local development and tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def write(self, event: AuditEvent) -> None:
        """Append an audit event in insertion order."""
        self.events.append(event)


@dataclass(frozen=True)
class ToolPolicy:
    """Allowlist of tools available to a tenant/actor pair."""

    allowed_tools: frozenset[str]
    approval_required_tools: frozenset[str] = frozenset()

    def allows(self, tool_name: str) -> bool:
        """Return whether the exact tool name is allowlisted."""
        return tool_name in self.allowed_tools

    def requires_approval(self, tool_name: str) -> bool:
        """Return whether a tool requires explicit human approval."""
        return tool_name in self.approval_required_tools


class PromptInjectionGuard:
    """Reject common instruction-hijacking patterns in untrusted evidence."""

    _blocked_phrases = (
        "ignore previous instructions",
        "ignore all previous instructions",
        "reveal the system prompt",
        "call the tool",
        "execute this command",
    )

    def validate(self, content: str) -> None:
        """Raise when content contains a known instruction-control phrase."""
        normalized = " ".join(content.lower().split())
        if any(phrase in normalized for phrase in self._blocked_phrases):
            raise PromptInjectionError("untrusted content contains tool-control instructions")


class AuthorizedToolExecutor:
    """Enforce prompt screening, authorization, and audit logging around tools."""

    def __init__(self, policy: ToolPolicy, audit_sink: AuditSink) -> None:
        self._policy = policy
        self._audit_sink = audit_sink

    async def execute(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        tool_name: str,
        action: str,
        arguments: dict[str, object],
        approval_id: UUID | None = None,
    ) -> dict[str, object]:
        """Authorize a bounded tool action and return an auditable result."""
        allowed = self._policy.allows(tool_name)
        approval_missing = self._policy.requires_approval(tool_name) and approval_id is None
        reason = (
            "tool is not allowlisted"
            if not allowed
            else "human approval is required"
            if approval_missing
            else None
        )
        await self._audit_sink.write(
            AuditEvent(
                event_id=uuid4(),
                tenant_id=tenant_id,
                actor_id=actor_id,
                tool_name=tool_name,
                action=action,
                allowed=allowed,
                reason=reason,
                approval_id=approval_id,
                created_at=datetime.now(UTC),
            )
        )
        if not allowed:
            raise ToolAuthorizationError(reason or "tool access denied")
        if approval_missing:
            raise ApprovalRequiredError(reason or "human approval is required")
        return {"tool": tool_name, "action": action, "arguments": arguments}
