"""Fixtures: a real table + GSI1 + KMS key against LocalStack, created once per session."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

os.environ.setdefault("MF_AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("MF_AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from modelforge_db.client import GSI1_NAME, get_dynamodb_resource, get_kms_client  # noqa: E402


@pytest.fixture(scope="session")
def dynamodb_table_name() -> Iterator[str]:
    table_name = f"modelforge-test-{uuid.uuid4().hex[:8]}"
    resource = get_dynamodb_resource()
    try:
        resource.meta.client.list_tables(Limit=1)
    except (EndpointConnectionError, ClientError) as error:
        pytest.skip(f"LocalStack not reachable at {os.environ['MF_AWS_ENDPOINT_URL']}: {error}")

    resource.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": GSI1_NAME,
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    resource.meta.client.get_waiter("table_exists").wait(TableName=table_name)
    resource.meta.client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )

    yield table_name

    resource.meta.client.delete_table(TableName=table_name)


@pytest.fixture
def table(dynamodb_table_name: str) -> Any:
    return get_dynamodb_resource().Table(dynamodb_table_name)


@pytest.fixture(scope="session")
def kms_key_id(dynamodb_table_name: str) -> str:
    # dynamodb_table_name forces the LocalStack-reachability skip to run first.
    client = get_kms_client()
    response = client.create_key(Description="modelforge-test hf-token key")
    return response["KeyMetadata"]["KeyId"]


def unique_id() -> str:
    return uuid.uuid4().hex


def now_ms() -> int:
    return int(time.time() * 1000)
