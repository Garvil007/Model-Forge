"""DynamoDB table / KMS client construction. Endpoint is overridable for LocalStack."""

from __future__ import annotations

import os
from typing import Any

import boto3

TABLE_NAME = os.environ.get("MF_DYNAMODB_TABLE", "modelforge")
GSI1_NAME = "GSI1"


def _endpoint_url() -> str | None:
    return os.environ.get("MF_AWS_ENDPOINT_URL") or None


def _region() -> str:
    return os.environ.get("MF_AWS_REGION", "us-east-1")


def get_dynamodb_resource() -> Any:
    return boto3.resource("dynamodb", region_name=_region(), endpoint_url=_endpoint_url())


def get_kms_client() -> Any:
    return boto3.client("kms", region_name=_region(), endpoint_url=_endpoint_url())


def get_table() -> Any:
    return get_dynamodb_resource().Table(TABLE_NAME)
