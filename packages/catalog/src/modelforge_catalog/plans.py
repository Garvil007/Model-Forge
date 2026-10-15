"""Per-plan upload size limits and S3 retention. See docs/decisions.md ("Day 9")."""

from __future__ import annotations

from dataclasses import dataclass

_GIB = 1024**3


@dataclass(frozen=True, slots=True)
class PlanLimits:
    max_model_bytes: int
    max_dataset_bytes: int
    retention_days: int
    retention_tag: str


_FREE = PlanLimits(
    max_model_bytes=2 * _GIB, max_dataset_bytes=2 * _GIB, retention_days=7, retention_tag="7d"
)
_PAID = PlanLimits(
    max_model_bytes=5 * _GIB, max_dataset_bytes=5 * _GIB, retention_days=30, retention_tag="30d"
)

PLAN_LIMITS: dict[str, PlanLimits] = {"free": _FREE, "pro": _PAID, "team": _PAID}


def limits_for(plan: str) -> PlanLimits:
    """Limits for a plan name; unknown plans fall back to Free (fail closed, not open)."""
    return PLAN_LIMITS.get(plan, _FREE)
