"""BillingEventRepository: idempotency guard for Stripe webhook events.

Stripe retries webhook deliveries on timeout/5xx, and the same event can legitimately
arrive twice. `record_if_new` claims an event id with a conditional put — the first
caller gets True and processes the event, every later retry gets False and no-ops. No
read-then-write race: the condition is enforced by DynamoDB, not application code.
"""

from __future__ import annotations

import time
from typing import Any

from botocore.exceptions import ClientError

from ..client import get_table

_EVENT_TTL_SECONDS = 30 * 24 * 3600


def _stripe_event_pk(event_id: str) -> str:
    return f"STRIPEEVENT#{event_id}"


class BillingEventRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def record_if_new(self, event_id: str) -> bool:
        try:
            self._table.put_item(
                Item={
                    "PK": _stripe_event_pk(event_id),
                    "SK": "EVENT",
                    "ttl": int(time.time()) + _EVENT_TTL_SECONDS,
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise
        return True
