"""SQS-triggered Lambda: submits a Batch job for each queued job message.

Idempotent against SQS at-least-once redelivery and against a job that was canceled
before dispatch (`POST /jobs/{id}/cancel` on a still-queued job just flips its status —
there's no cheap way to pull a specific message back out of SQS, so "queued jobs
dropped" is enforced here, at dispatch time, by skipping anything whose status is no
longer "queued").

Partial-batch handling: each record is processed independently and a failure on one
record is caught and logged, not re-raised, so one bad record doesn't block the rest of
the batch (SQS event source mappings here use batch size 1 anyway, so in practice each
invocation has exactly one record — this is defensive, not load-bearing).
"""

from __future__ import annotations

from typing import Any

from modelforge_catalog import OPERATIONS, job_messages
from modelforge_db.repositories.jobs import JobRepository

from .batch_client import get_batch_client

_OPERATIONS_BY_ID = {op.id: op for op in OPERATIONS}


def _job_definition_for(worker_image: str) -> str:
    return f"{worker_image}-job-def"


def _batch_queue_for(queue: str) -> str:
    return f"{queue}-queue"


def _process_record(body: str, *, jobs: JobRepository, batch_client: Any) -> None:
    message = job_messages.parse_message(body)
    try:
        job = jobs.get(message.user_id, message.job_id)
    except Exception:  # noqa: BLE001 — NotFoundError or similar: nothing to dispatch
        return
    if job.status != "queued":
        return  # already dispatched (redelivery) or canceled before dispatch

    operation = _OPERATIONS_BY_ID.get(message.operation_id)
    if operation is None:
        jobs.update_progress(
            message.user_id,
            message.job_id,
            status="failed",
            progress_percent=0,
            error={
                "code": "unsupported_operator",
                "message": f"unknown operation {message.operation_id!r}",
            },
        )
        return

    batch_job_id = batch_client.submit_job(
        message.job_id,
        _job_definition_for(operation.worker_image),
        _batch_queue_for(operation.queue),
        message_body=body,
    )
    jobs.set_batch_job_id(message.user_id, message.job_id, batch_job_id)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    jobs = JobRepository()
    batch_client = get_batch_client()

    processed = 0
    for record in event.get("Records", []):
        try:
            _process_record(record["body"], jobs=jobs, batch_client=batch_client)
            processed += 1
        except Exception as error:  # noqa: BLE001 — log and move on, see module docstring
            print(f"modelforge-dispatcher: error processing record: {error}")

    return {"processed": processed}
