"""Liveness proxy for a running job: periodically re-writes its own status so `updatedAt`
keeps advancing while a long-running op is in progress.

This is deliberately minimal — a proxy a future dashboard/alert could read staleness from,
not a watchdog. Nothing here detects a dead worker or requeues on its behalf.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from modelforge_db.repositories.jobs import JobRepository

_HEARTBEAT_INTERVAL_SECONDS = 30.0


@contextmanager
def heartbeat(
    user_id: str,
    job_id: str,
    *,
    job_repo: JobRepository | None = None,
    interval_seconds: float = _HEARTBEAT_INTERVAL_SECONDS,
) -> Iterator[None]:
    repo = job_repo if job_repo is not None else JobRepository()
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(interval_seconds):
            try:
                record = repo.get(user_id, job_id)
                repo.update_progress(
                    user_id,
                    job_id,
                    status=record.status,
                    progress_percent=record.progress_percent,
                    result=record.result,
                    error=record.error,
                    timings=record.timings,
                )
            except Exception:  # noqa: BLE001 — a heartbeat failure must never kill the job
                pass

    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
