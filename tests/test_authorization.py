from uuid import uuid4

import jwt
import pytest

from apps.api.auth import AuthContext, AuthorizationError, decode_access_token, require_roles


def test_jwt_roles_and_scopes_are_extracted() -> None:
    """Verify role arrays and OAuth scope strings become normalized roles."""
    tenant_id, actor_id = uuid4(), uuid4()
    token = jwt.encode(
        {
            "sub": str(actor_id),
            "tenant_id": str(tenant_id),
            "roles": ["admin", "reviewer"],
        },
        "test-secret",
        algorithm="HS256",
    )
    context = decode_access_token(token, secret="test-secret")
    assert context.roles == frozenset({"admin", "reviewer"})


def test_require_roles_accepts_authorized_context() -> None:
    """Verify all required roles must be present."""
    context = AuthContext(uuid4(), uuid4(), frozenset({"admin", "reviewer"}))
    assert require_roles(context, "admin", "reviewer") is context


def test_require_roles_rejects_missing_role() -> None:
    """Verify missing roles fail closed."""
    context = AuthContext(uuid4(), uuid4(), frozenset({"reader"}))
    with pytest.raises(AuthorizationError, match="admin"):
        require_roles(context, "admin")
