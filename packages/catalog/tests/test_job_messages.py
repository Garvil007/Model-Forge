"""Tests for job_messages.build_message/parse_message round-trip."""

from __future__ import annotations

import json

import pytest

from modelforge_catalog.job_messages import InvalidJobMessageError, build_message, parse_message


def test_build_then_parse_round_trips() -> None:
    body = build_message(
        job_id="job-1", user_id="user-1", model_id="model-1", operation_id="q_int8_dyn"
    )
    message = parse_message(body)
    assert message.job_id == "job-1"
    assert message.user_id == "user-1"
    assert message.model_id == "model-1"
    assert message.operation_id == "q_int8_dyn"
    assert message.version == 1


def test_built_message_uses_camel_case_keys() -> None:
    body = build_message(job_id="job-1", user_id="user-1", model_id="model-1", operation_id="op")
    raw = json.loads(body)
    assert set(raw) == {"jobId", "userId", "modelId", "operationId", "enqueuedAt", "version"}


def test_parse_rejects_non_json() -> None:
    with pytest.raises(InvalidJobMessageError):
        parse_message("not json")


def test_parse_rejects_wrong_version() -> None:
    with pytest.raises(InvalidJobMessageError):
        parse_message(json.dumps({"version": 99}))


def test_parse_rejects_invalid_ids() -> None:
    with pytest.raises(InvalidJobMessageError):
        parse_message(
            json.dumps(
                {
                    "jobId": "bad id with spaces",
                    "userId": "u",
                    "modelId": "m",
                    "operationId": "op",
                    "enqueuedAt": "now",
                    "version": 1,
                }
            )
        )


def test_parse_rejects_missing_enqueued_at() -> None:
    with pytest.raises(InvalidJobMessageError):
        parse_message(
            json.dumps(
                {"jobId": "j", "userId": "u", "modelId": "m", "operationId": "op", "version": 1}
            )
        )
