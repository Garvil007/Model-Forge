"""DataStack: the `modelforge` DynamoDB table, uploads/results S3 buckets, SQS job queues
with DLQs, and the KMS key that envelope-encrypts the Hugging Face token (see
docs/decisions.md's "Day 7" entry for the table's access-pattern design). Replaces the
separate StorageStack/QueueStack from Day 9/10 so every piece of durable state lives in
one stack.

Cost: on-demand DynamoDB billing (pay per request, nothing idle), point-in-time recovery
off in dev (a per-GB-month cost with no benefit for disposable dev data — turn it on for
prod), SSE-S3 (no per-request KMS cost on the buckets themselves), nothing always-on.
See docs/COSTS.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

_RULES_PATH = Path(__file__).resolve().parent.parent / "storage_rules.json"
_QUEUE_RETENTION = Duration.days(4)
_MAX_RECEIVE_COUNT = 3


def _load_rules() -> dict[str, Any]:
    return json.loads(_RULES_PATH.read_text())


def _lifecycle_rules(rules: dict[str, Any]) -> list[s3.LifecycleRule]:
    lifecycle = rules["lifecycle"]
    out = [
        s3.LifecycleRule(
            id=f"expire-retention-{tag['tagValue']}",
            tag_filters={tag["tagKey"]: tag["tagValue"]},
            expiration=Duration.days(tag["expirationDays"]),
        )
        for tag in lifecycle["retentionTagRules"]
    ]
    out.append(
        s3.LifecycleRule(
            id="expire-untagged-catch-all",
            prefix=lifecycle["untaggedCatchAllPrefix"],
            expiration=Duration.days(lifecycle["untaggedCatchAllExpirationDays"]),
        )
    )
    out.append(
        s3.LifecycleRule(
            id="abort-incomplete-multipart",
            abort_incomplete_multipart_upload_after=Duration.days(
                lifecycle["abortIncompleteMultipartUploadDays"]
            ),
        )
    )
    return out


def _bucket(scope: Construct, construct_id: str, env_name: str, rules: dict[str, Any]) -> s3.Bucket:
    cors = rules["cors"]
    is_dev = env_name == "dev"
    return s3.Bucket(
        scope,
        construct_id,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        encryption=s3.BucketEncryption.S3_MANAGED,
        enforce_ssl=True,
        versioned=False,
        removal_policy=RemovalPolicy.DESTROY if is_dev else RemovalPolicy.RETAIN,
        auto_delete_objects=is_dev,
        lifecycle_rules=_lifecycle_rules(rules),
        cors=[
            s3.CorsRule(
                allowed_methods=[s3.HttpMethods(m) for m in cors["allowedMethods"]],
                allowed_origins=cors["devOrigins"] if is_dev else [],
                allowed_headers=cors["allowedHeaders"],
                exposed_headers=cors["exposeHeaders"],
                max_age=cors["maxAgeSeconds"],
            )
        ],
    )


def _queue_with_dlq(
    scope: Construct, name: str, *, visibility_timeout: Duration
) -> tuple[sqs.Queue, sqs.Queue]:
    dlq = sqs.Queue(
        scope,
        f"{name}Dlq",
        queue_name=f"{name}-dlq",
        retention_period=_QUEUE_RETENTION,
        encryption=sqs.QueueEncryption.SQS_MANAGED,
    )
    queue = sqs.Queue(
        scope,
        name,
        queue_name=name,
        retention_period=_QUEUE_RETENTION,
        visibility_timeout=visibility_timeout,
        encryption=sqs.QueueEncryption.SQS_MANAGED,
        dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=_MAX_RECEIVE_COUNT, queue=dlq),
    )
    return queue, dlq


class DataStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, env_name: str, **kwargs: Any
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        is_dev = env_name == "dev"
        rules = _load_rules()

        self.uploads_bucket = _bucket(self, "UploadsBucket", env_name, rules)
        self.results_bucket = _bucket(self, "ResultsBucket", env_name, rules)

        self.cpu_jobs, self.cpu_jobs_dlq = _queue_with_dlq(
            self, "cpu-jobs", visibility_timeout=Duration.minutes(30)
        )
        self.gpu_jobs, self.gpu_jobs_dlq = _queue_with_dlq(
            self, "gpu-jobs", visibility_timeout=Duration.minutes(30)
        )
        self.system_jobs, self.system_jobs_dlq = _queue_with_dlq(
            self, "system-jobs", visibility_timeout=Duration.minutes(15)
        )

        self.table = dynamodb.Table(
            self,
            "Table",
            table_name="modelforge",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=not is_dev,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY if is_dev else RemovalPolicy.RETAIN,
        )
        self.table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(name="GSI1PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="GSI1SK", type=dynamodb.AttributeType.STRING),
        )

        self.hf_token_key = kms.Key(
            self,
            "HfTokenKey",
            alias="modelforge-hf-tokens",
            description="Envelope-encrypts the user's optional Hugging Face token",
            removal_policy=RemovalPolicy.DESTROY if is_dev else RemovalPolicy.RETAIN,
        )

        CfnOutput(self, "UploadsBucketName", value=self.uploads_bucket.bucket_name)
        CfnOutput(self, "ResultsBucketName", value=self.results_bucket.bucket_name)
        CfnOutput(self, "TableName", value=self.table.table_name)
        CfnOutput(self, "SystemJobsQueueUrl", value=self.system_jobs.queue_url)
        CfnOutput(self, "CpuJobsQueueUrl", value=self.cpu_jobs.queue_url)
        CfnOutput(self, "GpuJobsQueueUrl", value=self.gpu_jobs.queue_url)
        CfnOutput(self, "HfTokenKeyArn", value=self.hf_token_key.key_arn)
