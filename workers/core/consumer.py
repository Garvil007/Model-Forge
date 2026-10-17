"""Long-polls an SQS queue and dispatches each message via the given handler.

`handle_message` (system-jobs: detect_format/import_hf) and `handle_job_message` (real
compression/conversion jobs) are exposed standalone so a future Lambda/Batch entrypoint can
reuse them without the polling loop.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import boto3
from modelforge_catalog.job_messages import InvalidJobMessageError
from modelforge_catalog.job_messages import parse_message as parse_job_message
from modelforge_catalog.system_jobs import InvalidSystemJobMessageError
from modelforge_catalog.system_jobs import parse_message as parse_system_message

_WAIT_TIME_SECONDS = 20
_VISIBILITY_TIMEOUT_SECONDS = 15 * 60
_DROPPABLE_ERRORS = (InvalidSystemJobMessageError, InvalidJobMessageError)


def _sqs_client() -> Any:
    return boto3.client(
        "sqs",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def handle_message(body: str, *, approximate_receive_count: int = 1) -> None:
    # Imported here, not at module load: `core` and `ops` are sibling top-level packages
    # (see workers/pyproject.toml), and ops imports core.s3_reader, so importing ops at
    # core's module level would be a circular import.
    from ops import detect_format, import_hf

    message = parse_system_message(body)
    if message.kind == "detect_format":
        detect_format.handle_detect_format(
            user_id=message.user_id,
            model_id=message.model_id,
            approximate_receive_count=approximate_receive_count,
        )
    elif message.kind == "import_hf":
        import_hf.handle_import_hf(user_id=message.user_id, model_id=message.model_id)


def handle_job_message(body: str, *, approximate_receive_count: int = 1) -> None:
    """Dispatches a real compression/conversion job message to the runner."""
    from . import runner

    message = parse_job_message(body)
    runner.run_job(
        job_id=message.job_id,
        user_id=message.user_id,
        model_id=message.model_id,
        operation_id=message.operation_id,
    )


def run_forever(queue_url: str, handler: Callable[..., None] = handle_message) -> None:
    sqs = _sqs_client()
    print(f"modelforge-workers: polling {queue_url}")
    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=_WAIT_TIME_SECONDS,
            VisibilityTimeout=_VISIBILITY_TIMEOUT_SECONDS,
            AttributeNames=["ApproximateReceiveCount"],
        )
        for message in response.get("Messages", []):
            receipt_handle = message["ReceiptHandle"]
            receive_count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1))
            try:
                handler(message["Body"], approximate_receive_count=receive_count)
            except _DROPPABLE_ERRORS as error:
                print(f"modelforge-workers: dropping malformed message: {error}")
            except Exception as error:  # noqa: BLE001 — log and leave for redrive/DLQ
                print(f"modelforge-workers: error handling message: {error}")
                continue
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
