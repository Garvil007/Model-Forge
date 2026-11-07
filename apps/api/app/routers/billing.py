"""Stripe Checkout/Customer Portal + webhook. Stripe is the only writer of truth for
whether a subscription is actually active — `/checkout-session` and `/portal-session`
only ever hand back a Stripe-hosted URL, they never touch `plan` themselves. Only the
webhook (`/webhook`) calls `UserRepository.set_plan`, and only after verifying Stripe's
signature, so the UI can never show "Pro" before Stripe has actually confirmed payment.
"""

from __future__ import annotations

from typing import Annotated, Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from modelforge_catalog.billing_plans import BILLING_PLANS
from modelforge_db.records import UserRecord
from modelforge_db.repositories.billing_events import BillingEventRepository
from modelforge_db.repositories.users import UserRepository

from ..auth import current_user, get_user_repository
from ..config import Settings, get_settings
from ..stripe_client import get_stripe_secret_key, get_stripe_webhook_secret

router = APIRouter(prefix="/billing", tags=["billing"])

_ACTIVE_SUBSCRIPTION_STATUSES = ("active", "trialing")


def get_billing_event_repository() -> BillingEventRepository:
    return BillingEventRepository()


@router.get("/plans")
def list_plans() -> list[dict[str, Any]]:
    return [
        {
            "id": plan.id,
            "name": plan.name,
            "monthlyPriceUsdCents": plan.monthly_price_usd_cents,
            "tagline": plan.tagline,
            "features": list(plan.features),
        }
        for plan in BILLING_PLANS
    ]


@router.post("/checkout-session")
def create_checkout_session(
    user: Annotated[UserRecord, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Stripe Checkout for the Pro subscription. `client_reference_id` plus the
    subscription's own metadata both carry the user id, so the webhook can attribute
    `checkout.session.completed` and later `customer.subscription.*` events without a
    second DynamoDB index just to map a Stripe customer id back to a user."""
    stripe.api_key = get_stripe_secret_key()
    prices = stripe.Price.list(lookup_keys=[settings.stripe_price_lookup_key_pro], limit=1)
    if not prices.data:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The Pro plan isn't set up in Stripe yet — ask an admin to create its Price.",
        )
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": prices.data[0].id, "quantity": 1}],
        client_reference_id=user.user_id,
        customer_email=user.email,
        subscription_data={"metadata": {"userId": user.user_id}},
        success_url=f"{settings.web_base_url}/settings?upgraded=1",
        cancel_url=f"{settings.web_base_url}/pricing",
    )
    return {"url": session.url}


@router.post("/portal-session")
def create_portal_session(
    user: Annotated[UserRecord, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if not user.stripe_customer_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "No billing account yet — upgrade to Pro first."
        )
    stripe.api_key = get_stripe_secret_key()
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.web_base_url}/settings",
    )
    return {"url": portal.url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    events: Annotated[BillingEventRepository, Depends(get_billing_event_repository)],
) -> dict[str, str]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, signature, get_stripe_webhook_secret())
    except (ValueError, stripe.error.SignatureVerificationError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe signature") from error

    if not events.record_if_new(event["id"]):
        return {"status": "duplicate"}  # already processed this delivery — idempotent no-op

    _apply_event(event, users)
    return {"status": "ok"}


def _apply_event(event: dict[str, Any], users: UserRepository) -> None:
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            users.set_plan(user_id, "pro", stripe_customer_id=customer_id)
        return

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        user_id = (data.get("metadata") or {}).get("userId")
        if not user_id:
            return
        plan = "pro" if data.get("status") in _ACTIVE_SUBSCRIPTION_STATUSES else "free"
        users.set_plan(user_id, plan)
        return

    if event_type == "customer.subscription.deleted":
        user_id = (data.get("metadata") or {}).get("userId")
        if user_id:
            users.set_plan(user_id, "free")
        return
