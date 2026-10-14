"""TTL retention windows. See docs/decisions.md ("Day 7: Single-table DynamoDB schema")."""

from __future__ import annotations

import time

JOB_EVENT_RETENTION_SECONDS = 14 * 24 * 3600
JOB_RETENTION_SECONDS = 90 * 24 * 3600
MODEL_RETENTION_SECONDS = 365 * 24 * 3600


def ttl_from_now(retention_seconds: int, *, now: float | None = None) -> int:
    return int((now if now is not None else time.time()) + retention_seconds)
