"""Internal SQS message schema for background jobs the UI never sees directly.

Deliberately separate from the user-facing OPERATIONS catalog (techniques.py/converts.py)
so these internal kinds aren't exported to the UI or tripped up by catalog parity tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, get_args

SystemJobKind = Literal["detect_format", "import_hf"]
_VALID_KINDS: frozenset[str] = frozenset(get_args(SystemJobKind))
_SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class InvalidSystemJobMessageError(ValueError):
    """Raised when a queued message doesn't match the expected schema."""


@dataclass(frozen=True, slots=True)
class SystemJobMessage:
    kind: SystemJobKind
    user_id: str
    model_id: str
    enqueued_at: str
    version: int = _SCHEMA_VERSION


def build_message(kind: SystemJobKind, *, user_id: str, model_id: str) -> str:
    if kind not in _VALID_KINDS:
        raise InvalidSystemJobMessageError(f"unknown kind: {kind!r}")
    message = SystemJobMessage(
        kind=kind,
        user_id=user_id,
        model_id=model_id,
        enqueued_at=datetime.now(UTC).isoformat(),
    )
    return json.dumps(asdict(message))


def parse_message(body: str) -> SystemJobMessage:
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as error:
        raise InvalidSystemJobMessageError(f"not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise InvalidSystemJobMessageError("message body must be a JSON object")
    if raw.get("version") != _SCHEMA_VERSION:
        raise InvalidSystemJobMessageError(f"unsupported version: {raw.get('version')!r}")
    kind = raw.get("kind")
    if kind not in _VALID_KINDS:
        raise InvalidSystemJobMessageError(f"unknown kind: {kind!r}")
    user_id = raw.get("userId")
    model_id = raw.get("modelId")
    for name, value in (("userId", user_id), ("modelId", model_id)):
        if not isinstance(value, str) or not _ID_RE.match(value):
            raise InvalidSystemJobMessageError(f"invalid {name}: {value!r}")
    enqueued_at = raw.get("enqueuedAt")
    if not isinstance(enqueued_at, str):
        raise InvalidSystemJobMessageError("missing enqueuedAt")
    return SystemJobMessage(
        kind=kind, user_id=user_id, model_id=model_id, enqueued_at=enqueued_at
    )
