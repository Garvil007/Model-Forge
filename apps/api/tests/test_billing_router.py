"""POST/GET /billing/* — Stripe is monkeypatched (no network, no real Stripe account
needed); the fake repos below are the same shape as test_jobs_router.py's."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import stripe
from fastapi.testclient import TestClient
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import UserRecord

from app.auth import current_user
from app.main import app
from app.routers import billing as billing_router

client = TestClient(app)

_USER = UserRecord(
    user_id="user-1",
    email="user@example.com",
    plan="free",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
)

_PRO_USER = UserRecord(
    user_id="user-2",
    email="pro@example.com",
    plan="pro",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
    stripe_customer_id="cus_test123",
)


class _FakeUserRepository:
    def __init__(self) -> None:
        self.plans: dict[str, tuple[str, str | None]] = {}

    def set_plan(self, user_id: str, plan: str, *, stripe_customer_id: str | None = None) -> None:
        if user_id == "missing-user":
            raise NotFoundError(f"user {user_id!r} not found")
        previous_customer_id = self.plans.get(user_id, (None, None))[1]
        self.plans[user_id] = (plan, stripe_customer_id or previous_customer_id)


class _FakeBillingEventRepository:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def record_if_new(self, event_id: str) -> bool:
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        return True


@pytest.fixture(autouse=True)
def _overrides(monkeypatch: pytest.MonkeyPatch) -> Any:
    user_repo = _FakeUserRepository()
    event_repo = _FakeBillingEventRepository()
    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[billing_router.get_user_repository] = lambda: user_repo
    app.dependency_overrides[billing_router.get_billing_event_repository] = lambda: event_repo
    monkeypatch.setattr(billing_router, "get_stripe_secret_key", lambda: "sk_test_fake")
    monkeypatch.setattr(billing_router, "get_stripe_webhook_secret", lambda: "whsec_fake")
    yield SimpleNamespace(users=user_repo, events=event_repo)
    app.dependency_overrides.clear()


def test_list_plans_returns_free_and_pro() -> None:
    response = client.get("/billing/plans")

    assert response.status_code == 200
    ids = [plan["id"] for plan in response.json()]
    assert ids == ["free", "pro"]


def test_checkout_session_returns_stripe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stripe.Price,
        "list",
        lambda **kwargs: SimpleNamespace(data=[SimpleNamespace(id="price_123")]),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "create",
        lambda **kwargs: SimpleNamespace(url="https://checkout.stripe.com/pay/cs_test_123"),
    )

    response = client.post("/billing/checkout-session")

    assert response.status_code == 200
    assert response.json() == {"url": "https://checkout.stripe.com/pay/cs_test_123"}


def test_checkout_session_503_when_price_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stripe.Price, "list", lambda **kwargs: SimpleNamespace(data=[]))

    response = client.post("/billing/checkout-session")

    assert response.status_code == 503


def test_portal_session_requires_existing_customer() -> None:
    response = client.post("/billing/portal-session")

    assert response.status_code == 400


def test_portal_session_returns_stripe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    app.dependency_overrides[current_user] = lambda: _PRO_USER
    monkeypatch.setattr(
        stripe.billing_portal.Session,
        "create",
        lambda **kwargs: SimpleNamespace(url="https://billing.stripe.com/session/test"),
    )

    response = client.post("/billing/portal-session")

    assert response.status_code == 200
    assert response.json() == {"url": "https://billing.stripe.com/session/test"}


def test_webhook_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise stripe.error.SignatureVerificationError("bad signature", "sig_header")

    monkeypatch.setattr(stripe.Webhook, "construct_event", _raise)

    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "bad"})

    assert response.status_code == 400


def test_webhook_checkout_completed_upgrades_user(
    monkeypatch: pytest.MonkeyPatch, _overrides: Any
) -> None:
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "user-1", "customer": "cus_new"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "ok"})

    assert response.status_code == 200
    assert _overrides.users.plans["user-1"] == ("pro", "cus_new")


def test_webhook_subscription_deleted_downgrades_user(
    monkeypatch: pytest.MonkeyPatch, _overrides: Any
) -> None:
    event = {
        "id": "evt_2",
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"userId": "user-1"}}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "ok"})

    assert response.status_code == 200
    assert _overrides.users.plans["user-1"][0] == "free"


def test_webhook_is_idempotent_on_duplicate_event_id(
    monkeypatch: pytest.MonkeyPatch, _overrides: Any
) -> None:
    event = {
        "id": "evt_3",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "user-1", "customer": "cus_dup"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    first = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "ok"})
    _overrides.users.plans["user-1"] = ("free", None)  # prove the 2nd delivery doesn't rerun
    second = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "ok"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert _overrides.users.plans["user-1"] == ("free", None)
