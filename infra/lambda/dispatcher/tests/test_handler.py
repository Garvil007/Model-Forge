from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from modelforge_catalog import job_messages

from dispatcher.handler import handler


def _event(*bodies: str) -> dict:
    return {"Records": [{"body": body} for body in bodies]}


def _message(job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn"):
    return job_messages.build_message(
        job_id=job_id, user_id=user_id, model_id=model_id, operation_id=operation_id
    )


def _fake_jobs(status: str):
    jobs = MagicMock()
    jobs.get.return_value = SimpleNamespace(status=status)
    return jobs


def _fake_users(plan: str = "free"):
    users = MagicMock()
    users.get_by_id.return_value = SimpleNamespace(plan=plan)
    return users


def _patch_common(monkeypatch, jobs, batch_client, *, users=None, gpu_kill_switch=False):
    monkeypatch.setattr("dispatcher.handler.JobRepository", lambda: jobs)
    monkeypatch.setattr("dispatcher.handler.UserRepository", lambda: users or _fake_users())
    monkeypatch.setattr("dispatcher.handler.get_batch_client", lambda: batch_client)
    monkeypatch.setattr("dispatcher.handler.gpu_kill_switch_enabled", lambda: gpu_kill_switch)


def test_submits_once_for_a_queued_job(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    batch_client.submit_job.return_value = "batch-123"
    _patch_common(monkeypatch, jobs, batch_client)

    body = _message()
    result = handler(_event(body))

    assert result == {"processed": 1}
    batch_client.submit_job.assert_called_once()
    args, kwargs = batch_client.submit_job.call_args
    assert args[0] == "job-1"
    assert args[1] == "cpu-torch-job-def"
    assert args[2] == "cpu-queue"
    assert kwargs["message_body"] == body
    assert kwargs["timeout_seconds"] == 30 * 60  # Free plan's max_job_minutes_cpu
    jobs.set_batch_job_id.assert_called_once_with("user-1", "job-1", "batch-123")


def test_redelivery_of_an_already_dispatched_job_is_skipped(monkeypatch):
    jobs = _fake_jobs("running")
    batch_client = MagicMock()
    _patch_common(monkeypatch, jobs, batch_client)

    handler(_event(_message()))

    batch_client.submit_job.assert_not_called()
    jobs.set_batch_job_id.assert_not_called()


def test_canceled_before_dispatch_is_skipped(monkeypatch):
    jobs = _fake_jobs("canceled")
    batch_client = MagicMock()
    _patch_common(monkeypatch, jobs, batch_client)

    handler(_event(_message()))

    batch_client.submit_job.assert_not_called()


def test_submit_failure_marks_the_job_failed_not_stuck_queued(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    batch_client.submit_job.side_effect = RuntimeError("AccessDeniedException")
    _patch_common(monkeypatch, jobs, batch_client)

    result = handler(_event(_message()))

    assert result == {"processed": 1}
    jobs.update_progress.assert_called_once_with(
        "user-1",
        "job-1",
        status="failed",
        progress_percent=0,
        error={"code": "unknown", "message": "dispatch failed: AccessDeniedException"},
    )
    jobs.set_batch_job_id.assert_not_called()


def test_multi_record_event_processes_all_records(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    batch_client.submit_job.return_value = "batch-xyz"
    _patch_common(monkeypatch, jobs, batch_client)

    bodies = [_message(job_id=f"job-{i}") for i in range(3)]
    result = handler(_event(*bodies))

    assert result == {"processed": 3}
    assert batch_client.submit_job.call_count == 3


def test_gpu_job_gets_the_gpu_timeout_for_the_users_plan(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    batch_client.submit_job.return_value = "batch-gpu"
    _patch_common(monkeypatch, jobs, batch_client, users=_fake_users("pro"))

    handler(_event(_message(operation_id="q_gptq")))

    _, kwargs = batch_client.submit_job.call_args
    assert kwargs["timeout_seconds"] == 60 * 60  # pro plan's max_job_minutes_gpu


def test_gpu_kill_switch_fails_the_job_without_dispatching(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    _patch_common(monkeypatch, jobs, batch_client, gpu_kill_switch=True)

    handler(_event(_message(operation_id="q_gptq")))

    batch_client.submit_job.assert_not_called()
    jobs.update_progress.assert_called_once_with(
        "user-1",
        "job-1",
        status="failed",
        progress_percent=0,
        error={"code": "gpu_kill_switch", "message": "GPU jobs are temporarily paused."},
    )
