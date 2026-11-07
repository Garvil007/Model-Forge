"""Post-deploy smoke test for the dev environment: sign in as a real Cognito test user,
upload a tiny FP32 ONNX model, run it through the `q_fp16` job end to end on real AWS
Batch, and confirm it succeeds.

Run after `cdk deploy` by `.github/workflows/deploy.yml`, never locally against dev by
hand on a whim (it burns a real ~Fargate-minute job and writes real S3/DynamoDB rows under
the test user's account) — use `make e2e-jobs` against LocalStack for iteration instead.

Required environment variables:
    MF_API_URL                 ApiStack's `ApiUrl` output (no trailing slash)
    MF_COGNITO_USER_POOL_ID    AuthStack's `UserPoolId` output
    MF_COGNITO_CLIENT_ID       AuthStack's `UserPoolClientId` output
    MF_COGNITO_REGION          AuthStack's `UserPoolRegion` output
    MF_SMOKE_TEST_EMAIL        pre-created Cognito test user's email
    MF_SMOKE_TEST_PASSWORD     that user's password

The test user is created once by hand (see docs/decisions.md, "CI smoke test user") —
this script only signs in, it never creates or resets the account.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any

import boto3
import numpy as np
import onnx
import onnx.helper as helper
import requests

_MATRIX_SIZE = 8
_JOB_TIMEOUT_SECONDS = 600
_POLL_INTERVAL_SECONDS = 10


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"smoke_test: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return value


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
    graph = helper.make_graph([node], "smoke-test-g", [x], [y], initializer=[weight])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


def _sign_in(pool_id: str, client_id: str, region: str, email: str, password: str) -> str:
    client = boto3.client("cognito-idp", region_name=region)
    response = client.admin_initiate_auth(
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return str(response["AuthenticationResult"]["IdToken"])


def _poll(fn: Any, predicate: Any, what: str) -> dict[str, Any]:
    deadline = time.monotonic() + _JOB_TIMEOUT_SECONDS
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = fn()
        if predicate(last):
            return last
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"timed out waiting for {what}; last response: {last}")


def main() -> None:
    api_url = _env("MF_API_URL").rstrip("/")
    id_token = _sign_in(
        _env("MF_COGNITO_USER_POOL_ID"),
        _env("MF_COGNITO_CLIENT_ID"),
        _env("MF_COGNITO_REGION"),
        _env("MF_SMOKE_TEST_EMAIL"),
        _env("MF_SMOKE_TEST_PASSWORD"),
    )
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {id_token}"})

    model_bytes = _tiny_onnx_bytes()
    filename = f"smoke-test-{uuid.uuid4().hex[:8]}.onnx"

    print(f"smoke_test: creating upload for {filename} ({len(model_bytes)} bytes)")
    upload = session.post(
        f"{api_url}/uploads", json={"filename": filename, "size": len(model_bytes)}
    )
    upload.raise_for_status()
    upload_body = upload.json()

    part_url = upload_body["partUrls"][0]
    put_response = requests.put(part_url, data=model_bytes)
    put_response.raise_for_status()

    print("smoke_test: completing upload")
    complete = session.post(
        f"{api_url}/uploads/{upload_body['uploadId']}/complete",
        json={
            "uploadId": upload_body["uploadId"],
            "model": {
                "filename": filename,
                "format": "onnx",
                "family": "generic",
                "bits": 32,
                "params": _MATRIX_SIZE * _MATRIX_SIZE,
                "size": len(model_bytes),
            },
        },
    )
    complete.raise_for_status()
    model_id = complete.json()["id"]

    print(f"smoke_test: waiting for model {model_id} format detection")

    def _get_model() -> dict[str, Any]:
        response = session.get(f"{api_url}/models/{model_id}")
        response.raise_for_status()
        return response.json()

    model = _poll(_get_model, lambda m: m["status"] != "checking", "model format detection")
    if model["status"] != "ready":
        raise RuntimeError(f"model format detection did not succeed: {model}")

    print(f"smoke_test: submitting q_fp16 job for model {model_id}")
    job = session.post(
        f"{api_url}/jobs", json={"modelId": model_id, "operationId": "q_fp16", "values": {}}
    )
    job.raise_for_status()
    job_id = job.json()["id"]

    print(f"smoke_test: waiting for job {job_id}")

    def _get_job() -> dict[str, Any]:
        response = session.get(f"{api_url}/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    final_job = _poll(_get_job, lambda j: j["status"] in ("succeeded", "failed"), "job completion")
    if final_job["status"] != "succeeded":
        raise RuntimeError(f"smoke test job failed: {final_job}")

    print(f"smoke_test: PASSED (job {job_id} succeeded)")


if __name__ == "__main__":
    main()
