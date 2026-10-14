"""JobEventRepository: append-only progress stream for a job, scoped to its owning user."""

from __future__ import annotations

import time
import uuid
from typing import Any

from boto3.dynamodb.conditions import Key

from ..client import get_table
from ..keys import job_event_pk, job_event_sk
from ..records import JobEventRecord
from ..ttl import JOB_EVENT_RETENTION_SECONDS, ttl_from_now


class JobEventRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def append(
        self, user_id: str, job_id: str, *, stage: str, message: str, percent: int | None = None
    ) -> JobEventRecord:
        timestamp_ms = time.time_ns() // 1_000_000
        unique_suffix = uuid.uuid4().hex[:8]
        ttl = ttl_from_now(JOB_EVENT_RETENTION_SECONDS)
        item = {
            "PK": job_event_pk(user_id, job_id),
            "SK": job_event_sk(timestamp_ms, unique_suffix),
            "entityType": "JOB_EVENT",
            "userId": user_id,
            "jobId": job_id,
            "stage": stage,
            "message": message,
            "percent": percent,
            "timestampMs": timestamp_ms,
            "ttl": ttl,
        }
        self._table.put_item(Item=item)
        return _to_record(item)

    def list_for_job(self, user_id: str, job_id: str, *, limit: int = 200) -> list[JobEventRecord]:
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(job_event_pk(user_id, job_id)) & Key("SK").begins_with("EVENT#")
            ),
            ScanIndexForward=True,
            Limit=limit,
        )
        return [_to_record(item) for item in response.get("Items", [])]


def _to_record(item: dict[str, Any]) -> JobEventRecord:
    return JobEventRecord(
        user_id=item["userId"],
        job_id=item["jobId"],
        stage=item["stage"],
        message=item["message"],
        percent=int(item["percent"]) if item.get("percent") is not None else None,
        timestamp_ms=int(item["timestampMs"]),
        ttl=int(item["ttl"]),
    )
