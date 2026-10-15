"""UploadRepository: short-lived S3 multipart upload sessions (2-day TTL)."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from ..client import get_table
from ..exceptions import NotFoundError
from ..keys import upload_sk, user_pk
from ..records import UploadRecord
from ..ttl import UPLOAD_SESSION_RETENTION_SECONDS, ttl_from_now
from .base import new_id, now_iso, raise_not_found_on_condition_failure


class UploadRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def create(
        self,
        user_id: str,
        *,
        kind: str,
        entity_id: str,
        filename: str,
        safe_name: str,
        s3_key: str,
        s3_upload_id: str,
        declared_size: int,
        part_size: int,
        total_parts: int,
        retention_tag: str,
    ) -> UploadRecord:
        upload_id = new_id()
        timestamp = now_iso()
        ttl = ttl_from_now(UPLOAD_SESSION_RETENTION_SECONDS)
        item = {
            "PK": user_pk(user_id),
            "SK": upload_sk(upload_id),
            "entityType": "UPLOAD",
            "userId": user_id,
            "uploadId": upload_id,
            "kind": kind,
            "entityId": entity_id,
            "filename": filename,
            "safeName": safe_name,
            "s3Key": s3_key,
            "s3UploadId": s3_upload_id,
            "declaredSize": declared_size,
            "partSize": part_size,
            "totalParts": total_parts,
            "status": "pending",
            "retentionTag": retention_tag,
            "createdAt": timestamp,
            "ttl": ttl,
        }
        self._table.put_item(Item=item)
        return _to_record(item)

    def get(self, user_id: str, upload_id: str) -> UploadRecord:
        response = self._table.get_item(Key={"PK": user_pk(user_id), "SK": upload_sk(upload_id)})
        item = response.get("Item")
        if item is None:
            raise NotFoundError(f"upload {upload_id!r} not found for user {user_id!r}")
        return _to_record(item)

    def mark_completed(self, user_id: str, upload_id: str) -> UploadRecord:
        """Flip pending -> completed. Conditional, so a retried complete call is safe:
        the second caller gets ConditionalCheckFailedException and should treat that as
        'already done' rather than an error."""
        try:
            response = self._table.update_item(
                Key={"PK": user_pk(user_id), "SK": upload_sk(upload_id)},
                UpdateExpression="SET #status = :completed",
                ConditionExpression="attribute_exists(PK) AND #status = :pending",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":completed": "completed", ":pending": "pending"},
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            raise_not_found_on_condition_failure(
                error, f"upload {upload_id!r} not found or already completed"
            )
            raise
        return _to_record(response["Attributes"])


def _to_record(item: dict[str, Any]) -> UploadRecord:
    return UploadRecord(
        user_id=item["userId"],
        upload_id=item["uploadId"],
        kind=item["kind"],
        entity_id=item["entityId"],
        filename=item["filename"],
        safe_name=item["safeName"],
        s3_key=item["s3Key"],
        s3_upload_id=item["s3UploadId"],
        declared_size=int(item["declaredSize"]),
        part_size=int(item["partSize"]),
        total_parts=int(item["totalParts"]),
        status=item["status"],
        retention_tag=item["retentionTag"],
        created_at=item["createdAt"],
        ttl=int(item["ttl"]),
    )
