"""AWS Batch submission, abstracted so local dev/tests don't need real Batch.

LocalStack Community has no Batch emulation, so `LocalBatchJobClient` runs the worker
in-process via `workers.core.consumer.handle_job_message` instead of actually submitting
anywhere — it exercises the real worker code path (S3, quantize op, DynamoDB writes) with
only the "is it containerized" layer stubbed out. `RealBatchJobClient` is the prod boto3
implementation, used once a real Batch compute environment is deployed.

Selection is via `MF_BATCH_CLIENT=local|real` (default "local": safe for dev, since a
missing/misconfigured Batch setup should never silently try to call real AWS).
"""

from __future__ import annotations

import os
from typing import Any, Protocol


class BatchJobClient(Protocol):
    def submit_job(
        self, job_id: str, job_definition: str, queue: str, *, message_body: str | None = None
    ) -> str:
        """Submit a Batch job for `job_id`, returning the Batch job id.

        `message_body` (the original SQS message body) is accepted by every
        implementation so the handler's call site is uniform, but only
        `LocalBatchJobClient` actually uses it — `RealBatchJobClient` ignores it, since a
        real Batch job reads the job id from its own container parameters, not from SQS.
        """
        ...

    def terminate_job(self, batch_job_id: str) -> None:
        """Terminate a running Batch job."""
        ...


class RealBatchJobClient:
    """Submits to real AWS Batch via boto3."""

    def __init__(self, client: Any = None) -> None:
        self._client = client if client is not None else _boto3_batch_client()

    def submit_job(
        self, job_id: str, job_definition: str, queue: str, *, message_body: str | None = None
    ) -> str:
        response = self._client.submit_job(
            jobName=f"job-{job_id}",
            jobQueue=queue,
            jobDefinition=job_definition,
            parameters={"jobId": job_id},
        )
        return response["jobId"]

    def terminate_job(self, batch_job_id: str) -> None:
        self._client.terminate_job(jobId=batch_job_id, reason="canceled by user")


class LocalBatchJobClient:
    """Dev/test stand-in: runs the worker in-process instead of submitting to Batch.

    `job_definition`/`queue` are meaningless without real Batch, so this implementation
    ignores them and instead requires `message_body` (the original SQS message) to hand
    straight to `workers.core.consumer.handle_job_message`, running the real worker
    synchronously in this process. This exercises the actual worker code (S3 download,
    the op, DynamoDB writes) with only the "runs in a container on Batch" layer stubbed.

    `terminate_job` is a no-op (logs only): by the time anyone could call it, the
    in-process `submit_job` has already run the job to completion synchronously, so
    there's nothing left running to terminate. A real Batch job can be mid-execution when
    terminated; this stand-in cannot model that.
    """

    def submit_job(
        self, job_id: str, job_definition: str, queue: str, *, message_body: str | None = None
    ) -> str:
        from workers.core import consumer

        if message_body is None:
            raise ValueError("LocalBatchJobClient.submit_job requires message_body")
        consumer.handle_job_message(message_body)
        return f"local-{job_id}"

    def terminate_job(self, batch_job_id: str) -> None:
        print(
            f"modelforge-dispatcher: LocalBatchJobClient.terminate_job({batch_job_id!r}) "
            f"is a no-op (job already ran synchronously in-process)"
        )


def _boto3_batch_client() -> Any:
    import boto3

    return boto3.client(
        "batch",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def get_batch_client() -> BatchJobClient:
    mode = os.environ.get("MF_BATCH_CLIENT", "local")
    if mode == "real":
        return RealBatchJobClient()
    return LocalBatchJobClient()
