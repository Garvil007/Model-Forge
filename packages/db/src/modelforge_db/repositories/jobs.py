"""JobRepository: per-user job state, listed newest-first via GSI1."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..client import GSI1_NAME, get_table
from ..exceptions import NotFoundError
from ..keys import gsi1sk_for_listing, job_sk, user_pk
from ..records import JobRecord
from ..ttl import JOB_RETENTION_SECONDS, ttl_from_now
from .base import decimalize, jsonify, new_id, now_iso, raise_not_found_on_condition_failure


class JobRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def create(
        self,
        user_id: str,
        *,
        operation_id: str,
        params: dict[str, Any],
        queue: str,
        model_id: str | None = None,
        cost_estimate: float | None = None,
    ) -> JobRecord:
        job_id = new_id()
        timestamp = now_iso()
        ttl = ttl_from_now(JOB_RETENTION_SECONDS)
        item = {
            "PK": user_pk(user_id),
            "SK": job_sk(job_id),
            "GSI1PK": user_pk(user_id),
            "GSI1SK": gsi1sk_for_listing("JOB", timestamp, job_id),
            "entityType": "JOB",
            "userId": user_id,
            "jobId": job_id,
            "operationId": operation_id,
            "params": decimalize(params),
            "queue": queue,
            "status": "queued",
            "progressPercent": 0,
            "result": None,
            "error": None,
            "timings": {},
            "costEstimate": decimalize(cost_estimate) if cost_estimate is not None else None,
            "modelId": model_id,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "ttl": ttl,
        }
        self._table.put_item(Item=item)
        return _to_record(item)

    def get(self, user_id: str, job_id: str) -> JobRecord:
        response = self._table.get_item(Key={"PK": user_pk(user_id), "SK": job_sk(job_id)})
        item = response.get("Item")
        if item is None:
            raise NotFoundError(f"job {job_id!r} not found for user {user_id!r}")
        return _to_record(item)

    def list_for_user(self, user_id: str, *, limit: int = 50) -> list[JobRecord]:
        response = self._table.query(
            IndexName=GSI1_NAME,
            KeyConditionExpression=(
                Key("GSI1PK").eq(user_pk(user_id)) & Key("GSI1SK").begins_with("JOB#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [_to_record(item) for item in response.get("Items", [])]

    def update_progress(
        self,
        user_id: str,
        job_id: str,
        *,
        status: str,
        progress_percent: int,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        timings: dict[str, Any] | None = None,
    ) -> JobRecord:
        try:
            response = self._table.update_item(
                Key={"PK": user_pk(user_id), "SK": job_sk(job_id)},
                UpdateExpression=(
                    "SET #status = :status, progressPercent = :progress, "
                    "#result = :result, #error = :error, timings = :timings, "
                    "updatedAt = :updatedAt"
                ),
                ConditionExpression="attribute_exists(PK)",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#result": "result",
                    "#error": "error",
                },
                ExpressionAttributeValues={
                    ":status": status,
                    ":progress": progress_percent,
                    ":result": decimalize(result),
                    ":error": decimalize(error),
                    ":timings": decimalize(timings or {}),
                    ":updatedAt": now_iso(),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as error_:
            raise_not_found_on_condition_failure(
                error_, f"job {job_id!r} not found for user {user_id!r}"
            )
            raise
        return _to_record(response["Attributes"])


def _to_record(item: dict[str, Any]) -> JobRecord:
    return JobRecord(
        user_id=item["userId"],
        job_id=item["jobId"],
        operation_id=item["operationId"],
        params=jsonify(item.get("params", {})),
        queue=item["queue"],
        status=item["status"],
        progress_percent=int(item["progressPercent"]),
        result=jsonify(item["result"]) if item.get("result") is not None else None,
        error=jsonify(item["error"]) if item.get("error") is not None else None,
        timings=jsonify(item.get("timings", {})),
        cost_estimate=(
            float(item["costEstimate"]) if item.get("costEstimate") is not None else None
        ),
        model_id=item.get("modelId"),
        created_at=item["createdAt"],
        updated_at=item["updatedAt"],
        ttl=int(item["ttl"]),
    )
