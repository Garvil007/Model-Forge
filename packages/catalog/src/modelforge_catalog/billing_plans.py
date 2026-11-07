"""User-facing billing plans: display copy + the Stripe Price lookup key for each paid
plan. Separate from `plans.py`'s `PlanLimits` (the operational quota/retention numbers
enforced server-side) — this is marketing-facing config, consumed by `GET /billing/plans`
and the `/pricing` page, but both ultimately describe the same two plans. See
docs/COSTS.md for the per-job cost math behind `monthly_price_usd_cents`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BillingPlan:
    id: str
    name: str
    monthly_price_usd_cents: int
    tagline: str
    features: tuple[str, ...]
    # None for Free — there's nothing to buy. Looked up against Stripe's Price API by
    # lookup_key (not a hardcoded Price id), so test-mode and live-mode Stripe accounts
    # can each have their own Price object without any code or config change.
    stripe_price_lookup_key: str | None


BILLING_PLANS: tuple[BillingPlan, ...] = (
    BillingPlan(
        id="free",
        name="Free",
        monthly_price_usd_cents=0,
        tagline="Start compressing models at no cost.",
        features=(
            "CPU compression and conversion methods",
            "2 GB max model size",
            "120 CPU-minutes / month",
            "7-day result retention",
            "2 concurrent jobs",
        ),
        stripe_price_lookup_key=None,
    ),
    BillingPlan(
        id="pro",
        name="Pro",
        monthly_price_usd_cents=2900,
        tagline="GPU methods, more quota, longer retention.",
        features=(
            "Everything in Free",
            "GPU methods (quantization-aware training, distillation, TensorRT, ...)",
            "5 GB max model size",
            "1000 CPU-minutes + 180 GPU-minutes / month",
            "30-day result retention",
            "10 concurrent jobs",
            "Priority support",
        ),
        stripe_price_lookup_key="modelforge_pro_monthly",
    ),
)

_BY_ID = {plan.id: plan for plan in BILLING_PLANS}


def billing_plan(plan_id: str) -> BillingPlan | None:
    return _BY_ID.get(plan_id)
