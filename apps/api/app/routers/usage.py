"""GET /usage — remaining monthly CPU/GPU quota and GPU kill-switch state, for the UI's
quota display. Separate from jobs.py's own quota *enforcement* (which happens inline in
`POST /jobs`) — this route only reports numbers, it never blocks anything.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from modelforge_catalog.plans import limits_for
from modelforge_db.kill_switch import gpu_kill_switch_enabled
from modelforge_db.records import UserRecord
from modelforge_db.repositories.usage import UsageRepository

from ..auth import current_user

router = APIRouter(prefix="/usage", tags=["usage"])


def get_usage_repository() -> UsageRepository:
    return UsageRepository()


def get_gpu_kill_switch() -> bool:
    return gpu_kill_switch_enabled()


def _current_year_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


@router.get("")
def get_usage_summary(
    user: Annotated[UserRecord, Depends(current_user)],
    usage: Annotated[UsageRepository, Depends(get_usage_repository)],
    gpu_kill_switch_on: Annotated[bool, Depends(get_gpu_kill_switch)],
) -> dict[str, Any]:
    limits = limits_for(user.plan)
    record = usage.get(user.user_id, _current_year_month())
    return {
        "plan": user.plan,
        "cpuSecondsUsed": record.cpu_seconds,
        "cpuSecondsLimit": limits.monthly_cpu_minutes * 60,
        "gpuSecondsUsed": record.gpu_seconds,
        "gpuSecondsLimit": limits.monthly_gpu_minutes * 60,
        "maxConcurrentJobs": limits.max_concurrent_jobs,
        "gpuKillSwitchOn": gpu_kill_switch_on,
    }
