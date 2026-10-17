"""Full local chain for q_int8_dyn: POST /jobs -> SQS -> dispatcher -> worker -> download.

Requires LocalStack reachable at MF_AWS_ENDPOINT_URL (skipped otherwise, same gate as
packages/db/tests/conftest.py). Exercises every piece built across Steps A-E without any
real AWS Batch/Lambda deploy: the dispatcher Lambda's `handler` is called directly with a
hand-built SQS event, and `MF_BATCH_CLIENT=local` makes it run the worker in-process.

NEVER RUN AGAINST LIVE SERVICES IN THIS SESSION (Docker Desktop was not running). Verified
only by static review + `pytest --collect-only` (confirms imports resolve and the test
collects). Before trusting this test, run:

    make up
    make e2e-jobs
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any, Iterator

import urllib.request

import boto3
import numpy as np
import onnx
import onnx.helper as helper
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient
from modelforge_db.client import get_table
from modelforge_db.repositories.models import ModelRepository

os.environ.setdefault("MF_AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("MF_AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("MF_AUTH_MODE", "local")
os.environ.setdefault("MF_UPLOADS_BUCKET", "mf-uploads")
os.environ.setdefault("MF_RESULTS_BUCKET", "mf-results")

_ENDPOINT = os.environ["MF_AWS_ENDPOINT_URL"]
_MATRIX_SIZE = 64  # same size Step D's test found actually shrinks after int8 quantization
_CPU_QUEUE_NAME = "cpu-jobs"


def _tiny_onnx_bytes() -> bytes:
    rng = np.random.default_rng(0)
    x = helper.make_tensor_value_info("X", onnx.TensorProto.FLOAT, [1, _MATRIX_SIZE])
    y = helper.make_tensor_value_info("Y", onnx.TensorProto.FLOAT, [1, _MATRIX_SIZE])
    weight = helper.make_tensor(
        "W",
        onnx.TensorProto.FLOAT,
        [_MATRIX_SIZE, _MATRIX_SIZE],
        rng.standard_normal([_MATRIX_SIZE, _MATRIX_SIZE]).astype(np.float32).flatten().tolist(),
    )
    node = helper.make_node("MatMul", ["X", "W"], ["Y"])
    graph = helper.make_graph([node], "g", [x], [y], initializer=[weight])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


@pytest.fixture(scope="module")
def localstack_or_skip() -> None:
    client = boto3.client(
        "sts",
        endpoint_url=_ENDPOINT,
        region_name=os.environ["MF_AWS_REGION"],
    )
    try:
        client.get_caller_identity()
    except (EndpointConnectionError, ClientError) as error:
        pytest.skip(f"LocalStack not reachable at {_ENDPOINT}: {error}")


@pytest.fixture
def s3_client(localstack_or_skip: None) -> Any:
    return boto3.client(
        "s3", endpoint_url=_ENDPOINT, region_name=os.environ["MF_AWS_REGION"]
    )


@pytest.fixture
def sqs_client(localstack_or_skip: None) -> Any:
    return boto3.client(
        "sqs", endpoint_url=_ENDPOINT, region_name=os.environ["MF_AWS_REGION"]
    )


@pytest.fixture
def cpu_queue_url(sqs_client: Any) -> str:
    response = sqs_client.get_queue_url(QueueName=_CPU_QUEUE_NAME)
    return str(response["QueueUrl"])


@pytest.fixture(autouse=True)
def _env(cpu_queue_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MF_CPU_JOBS_QUEUE_URL", cpu_queue_url)
    monkeypatch.setenv("MF_BATCH_CLIENT", "local")
    yield


@pytest.fixture
def user_id() -> str:
    return f"e2e-user-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def uploaded_model(s3_client: Any, user_id: str) -> tuple[str, bytes]:
    model_bytes = _tiny_onnx_bytes()
    key = f"users/{user_id}/models/{uuid.uuid4().hex}.onnx"
    s3_client.put_object(Bucket="mf-uploads", Key=key, Body=model_bytes)
    return key, model_bytes


@pytest.fixture
def model_record(uploaded_model: tuple[str, bytes], user_id: str) -> Any:
    key, model_bytes = uploaded_model
    repo = ModelRepository(table=get_table())
    return repo.create(
        user_id,
        filename="tiny.onnx",
        s3_key=key,
        size_bytes=len(model_bytes),
        format="onnx",
        family="generic",
        bits=32.0,
        status="ready",
    )


def _api_client(user_id: str) -> TestClient:
    os.environ["MF_LOCAL_DEV_USER_ID"] = user_id
    from app.main import create_app

    return TestClient(create_app())


def test_q_int8_dyn_end_to_end(
    model_record: Any, user_id: str, uploaded_model: tuple[str, bytes],
    sqs_client: Any, cpu_queue_url: str,
) -> None:
    _, original_bytes = uploaded_model
    client = _api_client(user_id)

    create_response = client.post(
        "/jobs",
        json={"modelId": model_record.model_id, "operationId": "q_int8_dyn", "values": {}},
    )
    assert create_response.status_code == 201, create_response.text
    job_id = create_response.json()["id"]

    received = sqs_client.receive_message(
        QueueUrl=cpu_queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=5
    )
    messages = received.get("Messages", [])
    assert messages, "expected a message on cpu-jobs"
    body = messages[0]["Body"]
    sqs_client.delete_message(
        QueueUrl=cpu_queue_url, ReceiptHandle=messages[0]["ReceiptHandle"]
    )

    from dispatcher.handler import handler as dispatcher_handler

    dispatcher_handler({"Records": [{"body": body}]}, None)

    get_response = client.get(f"/jobs/{job_id}")
    assert get_response.status_code == 200
    job = get_response.json()
    assert job["status"] == "succeeded", job
    assert [stage["status"] for stage in job["stages"]] == ["done", "done", "done"]
    assert job["result"]["outputBytes"] < len(original_bytes)

    download_response = client.get(f"/jobs/{job_id}/download")
    assert download_response.status_code == 200
    url = download_response.json()["url"]

    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 — presigned S3 URL, not user input
        downloaded = response.read()
    assert len(downloaded) == job["result"]["outputBytes"]
    reloaded = onnx.load_from_string(downloaded)
    onnx.checker.check_model(reloaded)
