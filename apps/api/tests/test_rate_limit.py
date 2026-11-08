"""app.rate_limit: per-user and per-IP rate limiting dependency, in isolation from any
one router — a fake RateLimitRepository stands in for the real DynamoDB-backed one."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from modelforge_db.records import UserRecord

from app.auth import current_user
from app.errors import register_error_handlers
from app.rate_limit import get_rate_limit_repository, rate_limit

_USER = UserRecord(
    user_id="user-1",
    email="user@example.com",
    plan="free",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
)


class _FakeRateLimitRepository:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def increment_and_check(
        self, scope: str, key: str, *, limit: int, window_seconds: int, now: float | None = None
    ) -> bool:
        bucket = f"{scope}:{key}"
        self.counts[bucket] = self.counts.get(bucket, 0) + 1
        return self.counts[bucket] <= limit


def _build_app(limiter: _FakeRateLimitRepository) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post(
        "/limited",
        dependencies=[
            rate_limit(
                "test.scope",
                user_limit=2,
                user_window_seconds=60,
                ip_limit=3,
                ip_window_seconds=60,
            )
        ],
    )
    def limited() -> dict[str, bool]:
        return {"ok": True}

    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[get_rate_limit_repository] = lambda: limiter
    return app


def test_requests_within_the_user_limit_succeed() -> None:
    client = TestClient(_build_app(_FakeRateLimitRepository()))

    for _ in range(2):
        response = client.post("/limited")
        assert response.status_code == 200


def test_exceeding_the_user_limit_returns_429() -> None:
    client = TestClient(_build_app(_FakeRateLimitRepository()))

    for _ in range(2):
        client.post("/limited")
    response = client.post("/limited")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_exceeding_the_ip_limit_returns_429(monkeypatch: Any) -> None:
    import app.rate_limit as rate_limit_module

    # Different user ids share the same client IP, so the IP bucket (limit=3) trips
    # before any single user's own bucket (limit=2) would.
    monkeypatch.setattr(rate_limit_module, "client_ip", lambda request: "203.0.113.1")
    limiter = _FakeRateLimitRepository()
    app = FastAPI()
    register_error_handlers(app)

    @app.post(
        "/limited",
        dependencies=[
            rate_limit_module.rate_limit(
                "test.scope",
                user_limit=100,
                user_window_seconds=60,
                ip_limit=1,
                ip_window_seconds=60,
            )
        ],
    )
    def limited() -> dict[str, bool]:
        return {"ok": True}

    app.dependency_overrides[get_rate_limit_repository] = lambda: limiter

    def _user_a() -> UserRecord:
        return _USER

    def _user_b() -> UserRecord:
        return UserRecord(
            user_id="user-2",
            email="other@example.com",
            plan="free",
            settings={},
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )

    app.dependency_overrides[current_user] = _user_a
    client = TestClient(app)
    assert client.post("/limited").status_code == 200

    app.dependency_overrides[current_user] = _user_b
    response = client.post("/limited")

    assert response.status_code == 429
