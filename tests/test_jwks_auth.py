from typing import Any
from uuid import uuid4

import jwt
from _pytest.monkeypatch import MonkeyPatch

from apps.api.auth import decode_jwks_access_token


class FakeSigningKey:
    key = "test-key"


class FakeJwkClient:
    def __init__(self, url: str) -> None:
        assert url == "https://identity.test/.well-known/jwks.json"

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        assert token == "signed-token"
        return FakeSigningKey()


def test_jwks_decoder_uses_provider_key_and_claims(monkeypatch: MonkeyPatch) -> None:
    """Verify JWKS key resolution feeds RS256 claim validation."""
    tenant_id, actor_id = uuid4(), uuid4()
    monkeypatch.setattr(jwt, "PyJWKClient", FakeJwkClient)

    def fake_decode(token: str, key: str, **kwargs: Any) -> dict[str, object]:
        assert token == "signed-token"
        assert key == "test-key"
        return {
            "sub": str(actor_id),
            "tenant_id": str(tenant_id),
            "roles": ["admin"],
        }

    monkeypatch.setattr(
        jwt,
        "decode",
        fake_decode,
    )

    context = decode_jwks_access_token(
        "signed-token",
        jwks_url="https://identity.test/.well-known/jwks.json",
        issuer="https://identity.test/",
        audience="axiomrag-api",
    )
    assert context.tenant_id == tenant_id
    assert context.actor_id == actor_id
    assert context.roles == frozenset({"admin"})