"""QueueStack: cpu-jobs/gpu-jobs (compression/conversion work, from Day 10) plus a
dedicated system-jobs queue for fast internal jobs (detect_format) that shouldn't wait
behind a Batch/Fargate cold start. Each gets its own DLQ with maxReceiveCount 3, matching
LocalStack's init-aws.sh.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_sqs as sqs
from constructs import Construct

_RETENTION = Duration.days(4)
_MAX_RECEIVE_COUNT = 3


def _queue_with_dlq(scope: Construct, name: str, *, visibility_timeout: Duration) -> sqs.Queue:
    dlq = sqs.Queue(
        scope, f"{name}Dlq", queue_name=f"{name}-dlq", retention_period=_RETENTION,
        encryption=sqs.QueueEncryption.SQS_MANAGED,
    )
    return sqs.Queue(
        scope,
        name,
        queue_name=name,
        retention_period=_RETENTION,
        visibility_timeout=visibility_timeout,
        encryption=sqs.QueueEncryption.SQS_MANAGED,
        dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=_MAX_RECEIVE_COUNT, queue=dlq),
    )


class QueueStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.cpu_jobs = _queue_with_dlq(self, "cpu-jobs", visibility_timeout=Duration.minutes(30))
        self.gpu_jobs = _queue_with_dlq(self, "gpu-jobs", visibility_timeout=Duration.minutes(30))
        self.system_jobs = _queue_with_dlq(
            self, "system-jobs", visibility_timeout=Duration.minutes(15)
        )

        CfnOutput(self, "SystemJobsQueueUrl", value=self.system_jobs.queue_url)
        CfnOutput(self, "CpuJobsQueueUrl", value=self.cpu_jobs.queue_url)
        CfnOutput(self, "GpuJobsQueueUrl", value=self.gpu_jobs.queue_url)
