"""core.heartbeat: periodically touches a job's updatedAt via JobRepository.update_progress."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from modelforge_db.records import JobRecord

from core.heartbeat import heartbeat


def _job() -> JobRecord:
    now = datetime.now(UTC).isoformat()
    return JobRecord(
        user_id="user-1",
        job_id="job-1",
        operation_id="q_int8_dyn",
        params={},
        queue="cpu",
        status="running",
        progress_percent=10,
        result=None,
        error=None,
        timings={},
        cost_estimate=None,
        model_id="model-1",
        created_at=now,
        updated_at=now,
        ttl=0,
    )


class _FakeJobRepository:
    def __init__(self, record: JobRecord) -> None:
        self.record = record
        self.touch_count = 0

    def get(self, user_id: str, job_id: str) -> JobRecord:
        return self.record

    def update_progress(self, user_id: str, job_id: str, *, status, progress_percent, result=None, error=None, timings=None) -> JobRecord:
        self.touch_count += 1
        return self.record


def test_heartbeat_beats_at_least_once_within_two_intervals() -> None:
    jobs = _FakeJobRepository(_job())
    with heartbeat("user-1", "job-1", job_repo=jobs, interval_seconds=0.05):
        time.sleep(0.15)
    assert jobs.touch_count >= 1


def test_heartbeat_stops_cleanly_on_exit() -> None:
    jobs = _FakeJobRepository(_job())
    with heartbeat("user-1", "job-1", job_repo=jobs, interval_seconds=0.05):
        pass
    count_at_exit = jobs.touch_count
    time.sleep(0.15)
    assert jobs.touch_count == count_at_exit  # thread stopped, no further beats
