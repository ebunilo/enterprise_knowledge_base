"""Access-token validation against a locally generated Keycloak-like key set."""

import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt

from app import oidc

ISSUER = "https://auth.example.test/realms/enterprise-rag"
CLIENT = "enterprise-rag"


def _keypair(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    public_jwk = jwk.construct(public_pem, "RS256").to_dict()
    public_jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_pem, public_jwk


KEY_PEM, KEY_JWK = _keypair("k1")
ROTATED_PEM, ROTATED_JWK = _keypair("k2")


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    state = {"keys": [KEY_JWK], "refreshes": 0}

    async def fake_get_jwks(force_refresh: bool = False):
        if force_refresh:
            state["refreshes"] += 1
            state["keys"] = [KEY_JWK, ROTATED_JWK]
        return {"keys": list(state["keys"])}

    monkeypatch.setattr(oidc, "get_jwks", fake_get_jwks)
    monkeypatch.setattr(oidc.oidc_config, "issuer", ISSUER)
    monkeypatch.setattr(oidc, "cache_get", lambda key: None)
    monkeypatch.setattr(oidc, "cache_set", lambda *a, **k: True)
    return state


def make_token(key=KEY_PEM, kid="k1", **overrides) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": "user-1", "azp": CLIENT, "aud": "account", "typ": "Bearer",
              "iat": now, "exp": now + 300, "tenant_id": "global-company"}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


async def test_keycloak_access_token_accepted_via_azp():
    claims = await oidc.validate_token(make_token())
    assert claims["sub"] == "user-1"


async def test_audience_mapper_token_accepted():
    assert await oidc.validate_token(make_token(aud=[CLIENT, "account"], azp="other")) is not None


async def test_web_client_token_with_api_audience_accepted(monkeypatch):
    # Realm setup: enterprise-rag-web adds enterprise-rag-api to `aud`; the backend validates as the API client.
    monkeypatch.setattr(oidc.settings, "oidc_client_id", "enterprise-rag-api")
    token = make_token(azp="enterprise-rag-web", aud=["enterprise-rag-api", "account"])
    assert await oidc.validate_token(token) is not None
    assert await oidc.validate_token(make_token(azp="enterprise-rag-web", aud="account")) is None


async def test_foreign_client_token_rejected():
    assert await oidc.validate_token(make_token(azp="some-other-app", aud="account")) is None


async def test_id_token_rejected():
    assert await oidc.validate_token(make_token(typ="ID", aud=CLIENT)) is None


async def test_expired_token_rejected():
    assert await oidc.validate_token(make_token(exp=int(time.time()) - 10)) is None


async def test_wrong_issuer_rejected():
    assert await oidc.validate_token(make_token(iss="https://evil.example/realms/x")) is None


async def test_signature_from_unknown_key_rejected():
    forged = make_token(key=ROTATED_PEM, kid="k1")  # claims kid k1, signed with another key
    assert await oidc.validate_token(forged) is None


async def test_key_rotation_refreshes_jwks_once(provider):
    assert await oidc.validate_token(make_token(key=ROTATED_PEM, kid="k2")) is not None
    assert provider["refreshes"] == 1


async def test_hs256_algorithm_confusion_rejected():
    token = jwt.encode({"iss": ISSUER, "sub": "x", "azp": CLIENT, "exp": int(time.time()) + 60},
                       "secret", algorithm="HS256", headers={"kid": "k1"})
    assert await oidc.validate_token(token) is None


async def test_garbage_token_rejected():
    assert await oidc.validate_token("not-a-jwt") is None
