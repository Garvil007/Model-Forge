"""core.consumer: dispatches system-jobs and real job messages to the right handler."""

from __future__ import annotations

from typing import Any

import pytest
from modelforge_catalog import job_messages
from modelforge_catalog import system_jobs

from core import consumer


def test_handle_job_message_parses_and_dispatches_to_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_run_job(**kwargs: Any) -> None:
        calls.append(kwargs)

    from core import runner

    monkeypatch.setattr(runner, "run_job", _fake_run_job)

    body = job_messages.build_message(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn"
    )
    consumer.handle_job_message(body)

    assert len(calls) == 1
    assert calls[0]["job_id"] == "job-1"
    assert calls[0]["user_id"] == "user-1"
    assert calls[0]["model_id"] == "model-1"
    assert calls[0]["operation_id"] == "q_int8_dyn"


def test_handle_job_message_invalid_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(job_messages.InvalidJobMessageError):
        consumer.handle_job_message("not json")


def test_handle_message_still_dispatches_detect_format(monkeypatch: pytest.MonkeyPatch) -> None:
    import ops.detect_format as detect_format_module

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        detect_format_module,
        "handle_detect_format",
        lambda **kwargs: calls.append(kwargs),
    )

    # Built by hand (camelCase) rather than via system_jobs.build_message: that function's
    # asdict() output round-trips in snake_case, which parse_message (expecting camelCase)
    # rejects — a pre-existing bug in system_jobs.py, out of scope here (consumer.py isn't
    # the owner of that module and this test only needs a body parse_message accepts).
    import json

    body = json.dumps(
        {
            "kind": "detect_format",
            "userId": "user-1",
            "modelId": "model-1",
            "enqueuedAt": "2026-01-01T00:00:00+00:00",
            "version": 1,
        }
    )
    consumer.handle_message(body, approximate_receive_count=2)

    assert len(calls) == 1
    assert calls[0]["user_id"] == "user-1"
    assert calls[0]["model_id"] == "model-1"
    assert calls[0]["approximate_receive_count"] == 2


def test_handle_message_invalid_body_raises_system_error() -> None:
    with pytest.raises(system_jobs.InvalidSystemJobMessageError):
        consumer.handle_message("not json")
