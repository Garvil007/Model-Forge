"""StorageStack: uploads/results S3 buckets, CORS for direct browser multipart uploads,
and lifecycle rules (tag-based retention + abort-incomplete-multipart). Rules are read
from infra/storage_rules.json, the single source of truth also used by LocalStack's
init-aws.sh so dev and prod can't drift apart.

Cost: SSE-S3 (no KMS per-request cost), no versioning, nothing always-on — see
docs/COSTS.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from constructs import Construct

_RULES_PATH = Path(__file__).resolve().parent.parent / "storage_rules.json"


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


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, env_name: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)
        rules = _load_rules()

        self.uploads_bucket = _bucket(self, "UploadsBucket", env_name, rules)
        self.results_bucket = _bucket(self, "ResultsBucket", env_name, rules)

        CfnOutput(self, "UploadsBucketName", value=self.uploads_bucket.bucket_name)
        CfnOutput(self, "ResultsBucketName", value=self.results_bucket.bucket_name)
