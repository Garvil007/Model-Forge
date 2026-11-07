from __future__ import annotations

from unittest.mock import MagicMock

from modelforge_catalog.job_messages import build_message

from cost_recorder.handler import handler


def _event(*, status="SUCCEEDED", queue="gpu-queue", started_at=1_000_000, stopped_at=1_600_000):
    message = build_message(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_gptq"
    )
    return {
        "detail": {
            "status": status,
            "jobQueue": queue,
            "startedAt": started_at,
            "stoppedAt": stopped_at,
            "parameters": {"message": message},
        }
    }


def test_records_gpu_usage_and_cost(monkeypatch):
    usage = MagicMock()
    jobs = MagicMock()
    monkeypatch.setattr("cost_recorder.handler.UsageRepository", lambda: usage)
    monkeypatch.setattr("cost_recorder.handler.JobRepository", lambda: jobs)

    result = handler(_event())

    assert result["recorded"] is True
    assert result["durationSeconds"] == 600
    usage.increment.assert_called_once()
    _, kwargs = usage.increment.call_args
    assert kwargs["cpu_seconds"] == 0
    assert kwargs["gpu_seconds"] == 600
    jobs.set_actual_cost.assert_called_once_with("user-1", "job-1", result["costActual"])


def test_records_cpu_usage_for_cpu_queue(monkeypatch):
    usage = MagicMock()
    jobs = MagicMock()
    monkeypatch.setattr("cost_recorder.handler.UsageRepository", lambda: usage)
    monkeypatch.setattr("cost_recorder.handler.JobRepository", lambda: jobs)

    handler(_event(queue="cpu-queue"))

    _, kwargs = usage.increment.call_args
    assert kwargs["cpu_seconds"] == 600
    assert kwargs["gpu_seconds"] == 0


def test_non_terminal_status_is_skipped(monkeypatch):
    usage = MagicMock()
    monkeypatch.setattr("cost_recorder.handler.UsageRepository", lambda: usage)

    result = handler(_event(status="RUNNING"))

    assert result == {"recorded": False, "reason": "not a terminal status"}
    usage.increment.assert_not_called()


def test_job_that_never_started_is_skipped(monkeypatch):
    usage = MagicMock()
    monkeypatch.setattr("cost_recorder.handler.UsageRepository", lambda: usage)

    result = handler(_event(started_at=None, stopped_at=None))

    assert result == {"recorded": False, "reason": "job never started"}
    usage.increment.assert_not_called()
