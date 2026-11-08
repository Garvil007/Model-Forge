"""RateLimitRepository: fixed-window request counters for per-user and per-IP rate
limiting (see apps/api/app/rate_limit.py).

Lambda invocations don't share process memory, so an in-process token bucket can't see
traffic from other warm instances — the single DynamoDB table every other piece of state
lives in is the only thing all invocations actually share. A fixed window (not a sliding
one or a true token bucket) is enough here: it under- rather than over-counts at window
edges, which only ever makes the limit slightly more permissive, never less safe.

Keyed under its own `RATELIMIT#` partition prefix so it never collides with the
`USER#...` item hierarchy the other per-user repositories use.
"""

from __future__ import annotations

import time
from typing import Any

from ..client import get_table

_TTL_SLACK_SECONDS = 60  # let a window's item outlive the window itself before it expires


def _pk(scope: str, key: str, window_start: int) -> str:
    return f"RATELIMIT#{scope}#{key}#{window_start}"


class RateLimitRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def increment_and_check(
        self, scope: str, key: str, *, limit: int, window_seconds: int, now: float | None = None
    ) -> bool:
        """Atomically count one more request for `key` in the current fixed window of
        `scope`, returning True iff this request is within `limit`. Safe under concurrent
        callers: the count comes from DynamoDB's own atomic ADD, not a read-modify-write."""
        current_time = now if now is not None else time.time()
        window_start = int(current_time - (current_time % window_seconds))
        response = self._table.update_item(
            Key={"PK": _pk(scope, key, window_start), "SK": "COUNT"},
            UpdateExpression="ADD #count :one SET #ttl = if_not_exists(#ttl, :ttl)",
            ExpressionAttributeNames={"#count": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":one": 1,
                ":ttl": window_start + window_seconds + _TTL_SLACK_SECONDS,
            },
            ReturnValues="UPDATED_NEW",
        )
        count = int(response["Attributes"]["count"])
        return count <= limit
