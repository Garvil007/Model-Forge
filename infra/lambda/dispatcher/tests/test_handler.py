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


def test_submits_once_for_a_queued_job(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    batch_client.submit_job.return_value = "batch-123"
    monkeypatch.setattr("dispatcher.handler.JobRepository", lambda: jobs)
    monkeypatch.setattr("dispatcher.handler.get_batch_client", lambda: batch_client)

    body = _message()
    result = handler(_event(body))

    assert result == {"processed": 1}
    batch_client.submit_job.assert_called_once()
    args, kwargs = batch_client.submit_job.call_args
    assert args[0] == "job-1"
    assert args[1] == "cpu-base-job-def"
    assert args[2] == "cpu-queue"
    assert kwargs["message_body"] == body
    jobs.set_batch_job_id.assert_called_once_with("user-1", "job-1", "batch-123")


def test_redelivery_of_an_already_dispatched_job_is_skipped(monkeypatch):
    jobs = _fake_jobs("running")
    batch_client = MagicMock()
    monkeypatch.setattr("dispatcher.handler.JobRepository", lambda: jobs)
    monkeypatch.setattr("dispatcher.handler.get_batch_client", lambda: batch_client)

    handler(_event(_message()))

    batch_client.submit_job.assert_not_called()
    jobs.set_batch_job_id.assert_not_called()


def test_canceled_before_dispatch_is_skipped(monkeypatch):
    jobs = _fake_jobs("canceled")
    batch_client = MagicMock()
    monkeypatch.setattr("dispatcher.handler.JobRepository", lambda: jobs)
    monkeypatch.setattr("dispatcher.handler.get_batch_client", lambda: batch_client)

    handler(_event(_message()))

    batch_client.submit_job.assert_not_called()


def test_multi_record_event_processes_all_records(monkeypatch):
    jobs = _fake_jobs("queued")
    batch_client = MagicMock()
    batch_client.submit_job.return_value = "batch-xyz"
    monkeypatch.setattr("dispatcher.handler.JobRepository", lambda: jobs)
    monkeypatch.setattr("dispatcher.handler.get_batch_client", lambda: batch_client)

    bodies = [_message(job_id=f"job-{i}") for i in range(3)]
    result = handler(_event(*bodies))

    assert result == {"processed": 3}
    assert batch_client.submit_job.call_count == 3
