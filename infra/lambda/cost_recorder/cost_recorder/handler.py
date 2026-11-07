"""EventBridge-triggered Lambda: on every Batch "Job State Change" event (filtered to
SUCCEEDED/FAILED by the rule in infra/stacks/batch_stack.py), computes the job's real
wall-clock duration from Batch's own `startedAt`/`stoppedAt`, records it as cpu_seconds or
gpu_seconds in the user's monthly `UsageRepository` counters, and writes an estimated
dollar cost onto the job's own `cost_actual` field.

The job id/user id aren't in the event's `jobName` alone (it's just `job-{job_id}`, no
user) — they come from `detail.parameters.message`, the original SQS message body the
dispatcher passed through at SubmitJob time (see batch_client.RealBatchJobClient and
job_messages.py). Every real Batch job carries this, since the dispatcher always sets it.

Cost here is a rough estimate (Spot price per vCPU/GPU-hour times the job's measured
duration) — not the account's real bill. The daily cost email (infra/lambda/cost_report)
reads the *actual* billed spend from Cost Explorer; this field exists so a user can see an
approximate per-job cost in the UI immediately, without waiting for Cost Explorer's
~24h data lag.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modelforge_catalog import job_messages
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.usage import UsageRepository

_TERMINAL_STATUSES = ("SUCCEEDED", "FAILED")

# Rough Spot $/hour for a g6.xlarge/g5.xlarge (1 GPU, 4 vCPU) and for a 1-vCPU/2-GiB
# Fargate Spot CPU job — see docs/COSTS.md for how these were derived. Re-check
# against `aws ec2 describe-spot-price-history` occasionally; Spot prices drift.
_GPU_COST_PER_HOUR = 0.55
_CPU_COST_PER_HOUR = 0.02


def _year_month(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).strftime("%Y-%m")


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    detail = event.get("detail", {})
    status = detail.get("status")
    if status not in _TERMINAL_STATUSES:
        return {"recorded": False, "reason": "not a terminal status"}

    started_at = detail.get("startedAt")
    stopped_at = detail.get("stoppedAt")
    if not started_at or not stopped_at:
        return {"recorded": False, "reason": "job never started"}

    message_body = detail.get("parameters", {}).get("message")
    if not message_body:
        return {"recorded": False, "reason": "no job message on the Batch job"}

    try:
        message = job_messages.parse_message(message_body)
    except job_messages.InvalidJobMessageError:
        return {"recorded": False, "reason": "unparseable job message"}

    duration_seconds = max(0, round((stopped_at - started_at) / 1000))
    is_gpu = "gpu" in detail.get("jobQueue", "")

    usage = UsageRepository()
    usage.increment(
        message.user_id,
        _year_month(stopped_at),
        cpu_seconds=0 if is_gpu else duration_seconds,
        gpu_seconds=duration_seconds if is_gpu else 0,
    )

    cost_per_hour = _GPU_COST_PER_HOUR if is_gpu else _CPU_COST_PER_HOUR
    cost_actual = round(duration_seconds / 3600 * cost_per_hour, 4)
    jobs = JobRepository()
    jobs.set_actual_cost(message.user_id, message.job_id, cost_actual)

    return {
        "recorded": True,
        "jobId": message.job_id,
        "durationSeconds": duration_seconds,
        "costActual": cost_actual,
    }
