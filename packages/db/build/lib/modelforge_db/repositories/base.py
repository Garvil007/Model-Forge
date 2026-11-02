"""Shared helpers for repository modules: ids, timestamps, Decimal<->JSON, error mapping."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from ..exceptions import NotFoundError


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def decimalize(value: Any) -> Any:
    """Recursively convert floats to Decimal so boto3 will accept them for DynamoDB."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decimalize(item) for item in value]
    return value


def jsonify(value: Any) -> Any:
    """Recursively convert DynamoDB Decimals back to int/float for application-level dicts."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {key: jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonify(item) for item in value]
    return value


def raise_not_found_on_condition_failure(error: ClientError, message: str) -> None:
    """Translate a failed `attribute_exists` condition to NotFoundError; re-raise anything else."""
    if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
        raise NotFoundError(message) from error
    raise error
