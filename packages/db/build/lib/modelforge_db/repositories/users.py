"""UserRepository: profile CRUD, email lookup, and encrypted Hugging Face token."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..client import GSI1_NAME, get_table
from ..encryption import KmsEncryptor
from ..exceptions import NotFoundError
from ..keys import email_gsi1pk, profile_sk, user_pk
from ..records import UserRecord
from .base import now_iso, raise_not_found_on_condition_failure


class UserRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def create(
        self,
        user_id: str,
        email: str,
        *,
        plan: str = "free",
        settings: dict[str, Any] | None = None,
    ) -> UserRecord:
        timestamp = now_iso()
        item = {
            "PK": user_pk(user_id),
            "SK": profile_sk(),
            "GSI1PK": email_gsi1pk(email),
            "GSI1SK": user_pk(user_id),
            "entityType": "USER",
            "userId": user_id,
            "email": email,
            "plan": plan,
            "settings": settings or {},
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        self._table.put_item(Item=item)
        return _to_record(item)

    def get_by_id(self, user_id: str) -> UserRecord:
        response = self._table.get_item(Key={"PK": user_pk(user_id), "SK": profile_sk()})
        item = response.get("Item")
        if item is None:
            raise NotFoundError(f"user {user_id!r} not found")
        return _to_record(item)

    def get_by_email(self, email: str) -> UserRecord | None:
        response = self._table.query(
            IndexName=GSI1_NAME,
            KeyConditionExpression=Key("GSI1PK").eq(email_gsi1pk(email)),
            Limit=1,
        )
        items = response.get("Items", [])
        return _to_record(items[0]) if items else None

    def update_settings(self, user_id: str, settings: dict[str, Any]) -> UserRecord:
        try:
            response = self._table.update_item(
                Key={"PK": user_pk(user_id), "SK": profile_sk()},
                UpdateExpression="SET settings = :settings, updatedAt = :updatedAt",
                ConditionExpression="attribute_exists(PK)",
                ExpressionAttributeValues={":settings": settings, ":updatedAt": now_iso()},
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            raise_not_found_on_condition_failure(error, f"user {user_id!r} not found")
            raise
        return _to_record(response["Attributes"])

    def set_hf_token(self, user_id: str, token: str, encryptor: KmsEncryptor) -> None:
        ciphertext = encryptor.encrypt(token)
        try:
            self._table.update_item(
                Key={"PK": user_pk(user_id), "SK": profile_sk()},
                UpdateExpression="SET hfTokenCiphertext = :ciphertext, updatedAt = :updatedAt",
                ConditionExpression="attribute_exists(PK)",
                ExpressionAttributeValues={":ciphertext": ciphertext, ":updatedAt": now_iso()},
            )
        except ClientError as error:
            raise_not_found_on_condition_failure(error, f"user {user_id!r} not found")
            raise

    def get_hf_token(self, user_id: str, encryptor: KmsEncryptor) -> str | None:
        record = self.get_by_id(user_id)
        if record.hf_token_ciphertext is None:
            return None
        return encryptor.decrypt(record.hf_token_ciphertext)


def _to_record(item: dict[str, Any]) -> UserRecord:
    return UserRecord(
        user_id=item["userId"],
        email=item["email"],
        plan=item["plan"],
        settings=dict(item.get("settings", {})),
        created_at=item["createdAt"],
        updated_at=item["updatedAt"],
        hf_token_ciphertext=item.get("hfTokenCiphertext"),
    )
