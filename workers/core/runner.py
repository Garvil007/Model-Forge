"""Placeholder job runner. Real per-operation logic lands in workers/ops/ from Day 11 onward."""

from __future__ import annotations

from typing import Any

from modelforge_catalog import OPERATIONS

_OPERATIONS_BY_ID = {op.id: op for op in OPERATIONS}


class UnknownOperationError(ValueError):
    pass


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    """Validate a job and return a stub result; real logic lands in workers/ops/ later."""
    operation_id = job.get("operation_id")
    if operation_id not in _OPERATIONS_BY_ID:
        raise UnknownOperationError(f"Unknown operation_id: {operation_id!r}")
    operation = _OPERATIONS_BY_ID[operation_id]
    return {
        "job_id": job.get("job_id"),
        "operation_id": operation.id,
        "queue": operation.queue,
        "status": "not_implemented",
    }


if __name__ == "__main__":
    print("modelforge-workers: no queue consumer yet (see docs/PROGRESS.md Day 10+).")

