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
    max_concurrent_jobs: int
    # Monthly ceiling on compute time, checked against `UsageRepository`'s
    # year-month counters before a job is queued.
    monthly_cpu_minutes: int
    monthly_gpu_minutes: int
    # Hard wall-clock cap per job, passed to Batch as `attemptDurationSeconds` at
    # SubmitJob time so a stuck job can't run (and bill) forever.
    max_job_minutes_cpu: int
    max_job_minutes_gpu: int


_FREE = PlanLimits(
    max_model_bytes=2 * _GIB,
    max_dataset_bytes=2 * _GIB,
    retention_days=7,
    retention_tag="7d",
    max_concurrent_jobs=2,
    monthly_cpu_minutes=120,
    monthly_gpu_minutes=15,
    max_job_minutes_cpu=30,
    max_job_minutes_gpu=20,
)
_PAID = PlanLimits(
    max_model_bytes=5 * _GIB,
    max_dataset_bytes=5 * _GIB,
    retention_days=30,
    retention_tag="30d",
    max_concurrent_jobs=10,
    monthly_cpu_minutes=1000,
    monthly_gpu_minutes=180,
    max_job_minutes_cpu=90,
    max_job_minutes_gpu=60,
)

PLAN_LIMITS: dict[str, PlanLimits] = {"free": _FREE, "pro": _PAID, "team": _PAID}


def limits_for(plan: str) -> PlanLimits:
    """Limits for a plan name; unknown plans fall back to Free (fail closed, not open)."""
    return PLAN_LIMITS.get(plan, _FREE)
