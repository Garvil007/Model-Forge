"""TTL retention windows. See docs/decisions.md ("Day 7: Single-table DynamoDB schema")."""

from __future__ import annotations

import time

JOB_EVENT_RETENTION_SECONDS = 14 * 24 * 3600
JOB_RETENTION_SECONDS = 90 * 24 * 3600
MODEL_RETENTION_SECONDS = 365 * 24 * 3600
UPLOAD_SESSION_RETENTION_SECONDS = 2 * 24 * 3600


def ttl_from_now(retention_seconds: int, *, now: float | None = None) -> int:
    return int((now if now is not None else time.time()) + retention_seconds)


def retention_seconds(days: int) -> int:
    """Convert a plan's object-retention days (Day 9) to a TTL window, +1 day of slack so
    the DynamoDB record outlives the S3 object it points at (see docs/decisions.md)."""
    return (days + 1) * 24 * 3600
