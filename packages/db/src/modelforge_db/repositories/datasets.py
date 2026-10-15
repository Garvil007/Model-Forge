"""DatasetRepository: per-user calibration/training/validation dataset metadata."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from ..client import GSI1_NAME, get_table
from ..exceptions import NotFoundError
from ..keys import dataset_sk, gsi1sk_for_listing, user_pk
from ..records import DatasetRecord
from ..ttl import MODEL_RETENTION_SECONDS, ttl_from_now
from .base import new_id, now_iso


class DatasetRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def create(
        self,
        user_id: str,
        *,
        kind: str,
        filename: str,
        s3_key: str,
        size_bytes: int,
        model_id: str | None = None,
        dataset_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> DatasetRecord:
        dataset_id = dataset_id or new_id()
        timestamp = now_iso()
        ttl = ttl_from_now(ttl_seconds if ttl_seconds is not None else MODEL_RETENTION_SECONDS)
        item = {
            "PK": user_pk(user_id),
            "SK": dataset_sk(dataset_id),
            "GSI1PK": user_pk(user_id),
            "GSI1SK": gsi1sk_for_listing("DATASET", timestamp, dataset_id),
            "entityType": "DATASET",
            "userId": user_id,
            "datasetId": dataset_id,
            "kind": kind,
            "filename": filename,
            "s3Key": s3_key,
            "sizeBytes": size_bytes,
            "modelId": model_id,
            "createdAt": timestamp,
            "ttl": ttl,
        }
        self._table.put_item(Item=item)
        return _to_record(item)

    def get(self, user_id: str, dataset_id: str) -> DatasetRecord:
        response = self._table.get_item(
            Key={"PK": user_pk(user_id), "SK": dataset_sk(dataset_id)}
        )
        item = response.get("Item")
        if item is None:
            raise NotFoundError(f"dataset {dataset_id!r} not found for user {user_id!r}")
        return _to_record(item)

    def list_for_user(self, user_id: str, *, limit: int = 50) -> list[DatasetRecord]:
        response = self._table.query(
            IndexName=GSI1_NAME,
            KeyConditionExpression=(
                Key("GSI1PK").eq(user_pk(user_id)) & Key("GSI1SK").begins_with("DATASET#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [_to_record(item) for item in response.get("Items", [])]

    def delete(self, user_id: str, dataset_id: str) -> None:
        self._table.delete_item(Key={"PK": user_pk(user_id), "SK": dataset_sk(dataset_id)})


def _to_record(item: dict[str, Any]) -> DatasetRecord:
    return DatasetRecord(
        user_id=item["userId"],
        dataset_id=item["datasetId"],
        kind=item["kind"],
        filename=item["filename"],
        s3_key=item["s3Key"],
        size_bytes=int(item["sizeBytes"]),
        model_id=item.get("modelId"),
        created_at=item["createdAt"],
        ttl=int(item["ttl"]),
    )
