"""core.runner: dispatch, idempotency, cancel/timeout/spot-interruption control flow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import JobEventRecord, JobRecord

from core import runner
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError


def _job(
    *,
    status: str = "queued",
    operation_id: str = "q_int8_dyn",
    retry_count: int = 0,
    progress_percent: int = 0,
) -> JobRecord:
    now = datetime.now(UTC).isoformat()
    return JobRecord(
        user_id="user-1",
        job_id="job-1",
        operation_id=operation_id,
        params={},
        queue="cpu",
        status=status,
        progress_percent=progress_percent,
        result=None,
        error=None,
        timings={},
        cost_estimate=None,
        model_id="model-1",
        created_at=now,
        updated_at=now,
        ttl=0,
        retry_count=retry_count,
    )


class _FakeJobRepository:
    def __init__(self, record: JobRecord) -> None:
        self.record = record
        self.update_calls: list[dict[str, Any]] = []

    def get(self, user_id: str, job_id: str) -> JobRecord:
        if (user_id, job_id) != (self.record.user_id, self.record.job_id):
            raise NotFoundError("not found")
        return self.record

    def update_progress(
        self,
        user_id: str,
        job_id: str,
        *,
        status: str,
        progress_percent: int,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        timings: dict[str, Any] | None = None,
    ) -> JobRecord:
        self.update_calls.append({"status": status, "progress_percent": progress_percent, "error": error})
        self.record = JobRecord(
            **{
                **self.record.__dict__,
                "status": status,
                "progress_percent": progress_percent,
                "result": result,
                "error": error,
                "timings": timings or self.record.timings,
            }
        )
        return self.record

    def increment_retry_count(self, user_id: str, job_id: str) -> JobRecord:
        self.record = JobRecord(**{**self.record.__dict__, "retry_count": self.record.retry_count + 1})
        return self.record


class _FakeJobEventRepository:
    def __init__(self) -> None:
        self.events: list[JobEventRecord] = []

    def append(
        self, user_id: str, job_id: str, *, stage: str, message: str, percent: int | None = None
    ) -> JobEventRecord:
        event = JobEventRecord(
            user_id=user_id,
            job_id=job_id,
            stage=stage,
            message=message,
            percent=percent,
            timestamp_ms=0,
            ttl=0,
        )
        self.events.append(event)
        return event


def test_run_job_rejects_unknown_operation_cleanly() -> None:
    jobs = _FakeJobRepository(_job(operation_id="does_not_exist"))
    events = _FakeJobEventRepository()

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="does_not_exist",
        job_repo=jobs, event_repo=events,
    )

    assert jobs.record.status == "failed"
    assert jobs.record.error["code"] == "unsupported_operator"


def test_run_job_fails_cleanly_for_known_but_unimplemented_operation() -> None:
    jobs = _FakeJobRepository(_job(operation_id="q_int8_static"))
    events = _FakeJobEventRepository()

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_static",
        job_repo=jobs, event_repo=events,
    )

    assert jobs.record.status == "failed"
    assert jobs.record.error["code"] == "unsupported_operator"


def test_run_job_is_idempotent_on_terminal_status() -> None:
    jobs = _FakeJobRepository(_job(status="succeeded"))
    events = _FakeJobEventRepository()

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn",
        job_repo=jobs, event_repo=events,
    )

    assert jobs.update_calls == []  # never touched — already terminal


def test_run_job_dispatches_registered_op_for_q_int8_dyn(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = _FakeJobRepository(_job())
    events = _FakeJobEventRepository()
    calls: list[str] = []

    def _op(
        *, control: runner.JobControl, event_repo: Any, user_id: str, job_id: str, **_: Any
    ) -> None:
        control.check()
        event_repo.append(user_id, job_id, stage="dispatched", message="real op was called")
        calls.append("dispatched")

    monkeypatch.setitem(runner._OPS_BY_OPERATION_ID, "q_int8_dyn", _op)

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn",
        job_repo=jobs, event_repo=events,
    )

    assert jobs.record.status == "running"
    assert calls == ["dispatched"]
    assert any(event.stage == "dispatched" for event in events.events)


def test_job_control_raises_canceled_when_status_is_canceled() -> None:
    jobs = _FakeJobRepository(_job(status="canceled"))
    import threading

    control = runner.JobControl("user-1", "job-1", jobs, threading.Event())

    with pytest.raises(JobCanceledError):
        control.check()


def test_job_control_raises_timeout_when_flag_is_set() -> None:
    jobs = _FakeJobRepository(_job())
    import threading

    flag = threading.Event()
    flag.set()
    control = runner.JobControl("user-1", "job-1", jobs, flag)

    with pytest.raises(JobTimeoutError):
        control.check()


def test_job_control_raises_spot_interrupted_once_when_simulated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_SIMULATE_SPOT_INTERRUPTION", "1")
    jobs = _FakeJobRepository(_job())
    import threading

    control = runner.JobControl("user-1", "job-1", jobs, threading.Event())

    with pytest.raises(SpotInterruptedError):
        control.check()
    control.check()  # second call: already simulated once, falls through to the status check


def test_run_job_canceled_mid_op_writes_canceled_event(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = _FakeJobRepository(_job())
    events = _FakeJobEventRepository()

    def _op(*, control: runner.JobControl, **_: Any) -> None:
        raise JobCanceledError("boom")

    monkeypatch.setitem(runner._OPS_BY_OPERATION_ID, "q_int8_dyn", _op)

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn",
        job_repo=jobs, event_repo=events,
    )

    assert any(event.stage == "canceled" for event in events.events)
    assert jobs.record.status == "running"  # cancel doesn't overwrite status again — no clobber


def test_run_job_timeout_mid_op_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = _FakeJobRepository(_job())
    events = _FakeJobEventRepository()

    def _op(*, control: runner.JobControl, **_: Any) -> None:
        raise JobTimeoutError("too slow")

    monkeypatch.setitem(runner._OPS_BY_OPERATION_ID, "q_int8_dyn", _op)

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn",
        job_repo=jobs, event_repo=events,
    )

    assert jobs.record.status == "failed"
    assert jobs.record.error["code"] == "timeout"


def test_run_job_spot_interrupted_requeues_once_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = _FakeJobRepository(_job())
    events = _FakeJobEventRepository()
    sent: list[dict[str, Any]] = []

    class _FakeSqs:
        def send_message(self, *, QueueUrl: str, MessageBody: str) -> None:
            sent.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})

    def _op(*, control: runner.JobControl, **_: Any) -> None:
        raise SpotInterruptedError("reclaimed")

    monkeypatch.setitem(runner._OPS_BY_OPERATION_ID, "q_int8_dyn", _op)

    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn",
        job_repo=jobs, event_repo=events, sqs_client=_FakeSqs(), queue_url="http://queue/cpu-jobs",
    )

    assert jobs.record.status == "queued"
    assert jobs.record.retry_count == 1
    assert len(sent) == 1

    # Second interruption: retry_count is now 1, so this time it fails instead of requeuing.
    runner.run_job(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn",
        job_repo=jobs, event_repo=events, sqs_client=_FakeSqs(), queue_url="http://queue/cpu-jobs",
    )

    assert jobs.record.status == "failed"
    assert jobs.record.error["code"] == "spot_interrupted"
    assert len(sent) == 1  # not requeued again
