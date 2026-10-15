"""ModelRepository: per-user model metadata, listed newest-first via GSI1."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..client import GSI1_NAME, get_table
from ..exceptions import NotFoundError
from ..keys import gsi1sk_for_listing, model_sk, user_pk
from ..records import ModelRecord
from ..ttl import MODEL_RETENTION_SECONDS, ttl_from_now
from .base import decimalize, jsonify, new_id, now_iso, raise_not_found_on_condition_failure


class ModelRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def create(
        self,
        user_id: str,
        *,
        filename: str,
        s3_key: str,
        size_bytes: int,
        format: str,
        family: str,
        bits: float | None = None,
        param_count: int | None = None,
        details: dict[str, Any] | None = None,
        status: str = "ready",
        model_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> ModelRecord:
        model_id = model_id or new_id()
        timestamp = now_iso()
        ttl = ttl_from_now(ttl_seconds if ttl_seconds is not None else MODEL_RETENTION_SECONDS)
        item = {
            "PK": user_pk(user_id),
            "SK": model_sk(model_id),
            "GSI1PK": user_pk(user_id),
            "GSI1SK": gsi1sk_for_listing("MODEL", timestamp, model_id),
            "entityType": "MODEL",
            "userId": user_id,
            "modelId": model_id,
            "filename": filename,
            "s3Key": s3_key,
            "sizeBytes": size_bytes,
            "format": format,
            "family": family,
            "bits": bits,
            "paramCount": param_count,
            "details": decimalize(details or {}),
            "status": status,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "ttl": ttl,
        }
        self._table.put_item(Item=item)
        return _to_record(item)

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        response = self._table.get_item(Key={"PK": user_pk(user_id), "SK": model_sk(model_id)})
        item = response.get("Item")
        if item is None:
            raise NotFoundError(f"model {model_id!r} not found for user {user_id!r}")
        return _to_record(item)

    def list_for_user(self, user_id: str, *, limit: int = 50) -> list[ModelRecord]:
        response = self._table.query(
            IndexName=GSI1_NAME,
            KeyConditionExpression=(
                Key("GSI1PK").eq(user_pk(user_id)) & Key("GSI1SK").begins_with("MODEL#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [_to_record(item) for item in response.get("Items", [])]

    def update_status(self, user_id: str, model_id: str, status: str) -> ModelRecord:
        try:
            response = self._table.update_item(
                Key={"PK": user_pk(user_id), "SK": model_sk(model_id)},
                UpdateExpression="SET #status = :status, updatedAt = :updatedAt",
                ConditionExpression="attribute_exists(PK)",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": status, ":updatedAt": now_iso()},
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            raise_not_found_on_condition_failure(
                error, f"model {model_id!r} not found for user {user_id!r}"
            )
            raise
        return _to_record(response["Attributes"])

    def delete(self, user_id: str, model_id: str) -> None:
        self._table.delete_item(Key={"PK": user_pk(user_id), "SK": model_sk(model_id)})

    def apply_detection(
        self,
        user_id: str,
        model_id: str,
        *,
        format: str,
        family: str,
        bits: float | None,
        param_count: int | None,
        details_patch: dict[str, Any],
        expected_status: str = "checking",
    ) -> ModelRecord:
        """Write detection results and flip status checking -> ready, idempotently."""
        try:
            response = self._table.update_item(
                Key={"PK": user_pk(user_id), "SK": model_sk(model_id)},
                UpdateExpression=(
                    "SET #status = :ready, #format = :format, family = :family, "
                    "bits = :bits, paramCount = :paramCount, details = :details, "
                    "updatedAt = :updatedAt"
                ),
                ConditionExpression="attribute_exists(PK) AND #status = :expected",
                ExpressionAttributeNames={"#status": "status", "#format": "format"},
                ExpressionAttributeValues={
                    ":ready": "ready",
                    ":expected": expected_status,
                    ":format": format,
                    ":family": family,
                    ":bits": decimalize(bits),
                    ":paramCount": param_count,
                    ":details": decimalize(details_patch),
                    ":updatedAt": now_iso(),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return self.get(user_id, model_id)
            raise
        return _to_record(response["Attributes"])

    def mark_failed(
        self, user_id: str, model_id: str, *, code: str, message: str
    ) -> ModelRecord:
        response = self._table.update_item(
            Key={"PK": user_pk(user_id), "SK": model_sk(model_id)},
            UpdateExpression="SET #status = :failed, details.detectionError = :error, updatedAt = :updatedAt",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":failed": "failed",
                ":error": {"code": code, "message": message},
                ":updatedAt": now_iso(),
            },
            ReturnValues="ALL_NEW",
        )
        return _to_record(response["Attributes"])


def _to_record(item: dict[str, Any]) -> ModelRecord:
    return ModelRecord(
        user_id=item["userId"],
        model_id=item["modelId"],
        filename=item["filename"],
        s3_key=item["s3Key"],
        size_bytes=int(item["sizeBytes"]),
        format=item["format"],
        family=item["family"],
        bits=float(item["bits"]) if item.get("bits") is not None else None,
        param_count=int(item["paramCount"]) if item.get("paramCount") is not None else None,
        details=jsonify(item.get("details", {})),
        status=item["status"],
        created_at=item["createdAt"],
        updated_at=item["updatedAt"],
        ttl=int(item["ttl"]),
    )
