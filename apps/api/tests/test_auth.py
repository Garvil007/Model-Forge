"""Cognito token verification tests — a fake JWKS client keeps these fully offline."""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import UserRecord

from app import auth as auth_module
from app.main import app

client = TestClient(app)

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test"
_CLIENT_ID = "test-client-id"
_SETTINGS_ENV = {
    "MF_COGNITO_USER_POOL_ID": "us-east-1_test",
    "MF_COGNITO_REGION": "us-east-1",
    "MF_COGNITO_CLIENT_ID": _CLIENT_ID,
}


class _FakeSigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class _FakeJwksClient:
    """Stands in for PyJWKClient so no network call happens during tests."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        return _FakeSigningKey(_PRIVATE_KEY.public_key())


class _FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, UserRecord] = {}

    def get_by_id(self, user_id: str) -> UserRecord:
        try:
            return self.users[user_id]
        except KeyError:
            raise NotFoundError(f"user {user_id!r} not found") from None

    def create(self, user_id: str, email: str) -> UserRecord:
        record = UserRecord(
            user_id=user_id,
            email=email,
            plan="free",
            settings={},
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        self.users[user_id] = record
        return record


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _SETTINGS_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(auth_module, "PyJWKClient", _FakeJwksClient)
    auth_module._jwks_clients.clear()


@pytest.fixture
def fake_users() -> Any:
    fake = _FakeUserRepository()
    app.dependency_overrides[auth_module.get_user_repository] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def _make_token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "token_use": "access",
        "client_id": _CLIENT_ID,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + 3600,
        "email": "user@example.com",
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-kid"})


def test_me_without_token_returns_401(fake_users: Any) -> None:
    response = client.get("/me")
    assert response.status_code == 401


def test_me_rejects_id_token(fake_users: Any) -> None:
    token = _make_token(token_use="id")
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_rejects_wrong_client(fake_users: Any) -> None:
    token = _make_token(client_id="someone-elses-client")
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_rejects_expired_token(fake_users: Any) -> None:
    now = int(time.time())
    token = _make_token(iat=now - 7200, exp=now - 3600)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_creates_user_on_first_request_then_reuses_it(fake_users: Any) -> None:
    token = _make_token()
    headers = {"Authorization": f"Bearer {token}"}

    first = client.get("/me", headers=headers)
    assert first.status_code == 200
    assert first.json() == {"userId": "user-123", "email": "user@example.com"}

    second = client.get("/me", headers=headers)
    assert second.status_code == 200
    assert len(fake_users.users) == 1
