"""SQS message schema for real compression/conversion jobs.

Deliberately separate from system_jobs.py's SystemJobMessage (detect_format/import_hf) —
this carries a user-created job's identity only; the worker re-reads params from
JobRepository rather than trusting a copy in the message, so the two never drift.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

_SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class InvalidJobMessageError(ValueError):
    """Raised when a queued job message doesn't match the expected schema."""


@dataclass(frozen=True, slots=True)
class JobMessage:
    job_id: str
    user_id: str
    model_id: str
    operation_id: str
    enqueued_at: str
    version: int = _SCHEMA_VERSION


def build_message(*, job_id: str, user_id: str, model_id: str, operation_id: str) -> str:
    message = JobMessage(
        job_id=job_id,
        user_id=user_id,
        model_id=model_id,
        operation_id=operation_id,
        enqueued_at=datetime.now(UTC).isoformat(),
    )
    return json.dumps(
        {
            "jobId": message.job_id,
            "userId": message.user_id,
            "modelId": message.model_id,
            "operationId": message.operation_id,
            "enqueuedAt": message.enqueued_at,
            "version": message.version,
        }
    )


def parse_message(body: str) -> JobMessage:
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as error:
        raise InvalidJobMessageError(f"not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise InvalidJobMessageError("message body must be a JSON object")
    if raw.get("version") != _SCHEMA_VERSION:
        raise InvalidJobMessageError(f"unsupported version: {raw.get('version')!r}")

    job_id = raw.get("jobId")
    user_id = raw.get("userId")
    model_id = raw.get("modelId")
    operation_id = raw.get("operationId")
    for name, value in (
        ("jobId", job_id),
        ("userId", user_id),
        ("modelId", model_id),
    ):
        if not isinstance(value, str) or not _ID_RE.match(value):
            raise InvalidJobMessageError(f"invalid {name}: {value!r}")
    if not isinstance(operation_id, str) or not operation_id:
        raise InvalidJobMessageError(f"invalid operationId: {operation_id!r}")

    enqueued_at = raw.get("enqueuedAt")
    if not isinstance(enqueued_at, str):
        raise InvalidJobMessageError("missing enqueuedAt")

    return JobMessage(
        job_id=job_id,
        user_id=user_id,
        model_id=model_id,
        operation_id=operation_id,
        enqueued_at=enqueued_at,
    )
