"""ApiStack: FastAPI (apps/api, via Mangum) on a container-image Lambda, fronted by an
API Gateway HTTP API. 7-day log retention keeps CloudWatch Logs from growing forever.

No reserved concurrency is set: this account's current Lambda concurrency limit is only
10 (`aws lambda get-account-settings`, a new-account default AWS hasn't auto-raised yet),
and AWS requires at least 10 execution slots to stay unreserved account-wide — reserving
*any* amount here fails deploy outright (`CREATE_FAILED`: "decreases account's
UnreservedConcurrentExecution below its minimum value of [10]"). Revisit once the
account's limit is raised (AWS Support quota increase, usually automatic after some
account age/usage) — a `reserved_concurrent_executions` cap is still the right spend
control once there's headroom to set one below the account ceiling.

Cost: HTTP API has no fixed monthly fee (pay per request + per-GB data transfer); the
Lambda is pay-per-invocation (no provisioned concurrency); CloudWatch Logs at 7-day
retention charges only for ingestion + a week of storage, not an unbounded log group. See
docs/COSTS.md.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class ApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        table: dynamodb.ITable,
        uploads_bucket: s3.IBucket,
        results_bucket: s3.IBucket,
        system_jobs_queue: sqs.IQueue,
        cpu_jobs_queue: sqs.IQueue,
        gpu_jobs_queue: sqs.IQueue,
        hf_token_key: kms.IKey,
        cognito_user_pool_id: str,
        cognito_region: str,
        cognito_client_id: str,
        api_code_path: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        function = lambda_.DockerImageFunction(
            self,
            "ApiFunction",
            function_name=f"modelforge-api-{env_name}",
            code=lambda_.DockerImageCode.from_image_asset(
                api_code_path,
                file="apps/api/Dockerfile",
                # The build context is the repo root (Dockerfile needs packages/catalog,
                # packages/db and apps/api); exclude everything else so CDK doesn't tar
                # up unrelated heavy trees (node_modules, local venvs, other worker
                # images, docs) before invoking `docker build`.
                exclude=[
                    ".git",
                    ".github",
                    ".claude",
                    ".ruff_cache",
                    "**/__pycache__",
                    "**/.pytest_cache",
                    "**/*.egg-info",
                    "infra",
                    "apps/web",
                    "workers",
                    "docs",
                ],
            ),
            timeout=Duration.seconds(29),  # HTTP API's own hard integration timeout is 30s
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "MF_APP_NAME": "ModelForge API",
                "MF_ENVIRONMENT": env_name,
                "MF_AUTH_MODE": "cognito",
                "MF_COGNITO_USER_POOL_ID": cognito_user_pool_id,
                "MF_COGNITO_REGION": cognito_region,
                "MF_COGNITO_CLIENT_ID": cognito_client_id,
                "MF_AWS_REGION": self.region,
                "MF_UPLOADS_BUCKET": uploads_bucket.bucket_name,
                "MF_RESULTS_BUCKET": results_bucket.bucket_name,
                "MF_SYSTEM_JOBS_QUEUE_URL": system_jobs_queue.queue_url,
                "MF_CPU_JOBS_QUEUE_URL": cpu_jobs_queue.queue_url,
                "MF_GPU_JOBS_QUEUE_URL": gpu_jobs_queue.queue_url,
                "MF_HF_TOKEN_KMS_KEY_ID": hf_token_key.key_id,
            },
        )

        table.grant_read_write_data(function)
        uploads_bucket.grant_read_write(function)
        results_bucket.grant_read_write(function)
        system_jobs_queue.grant_send_messages(function)
        cpu_jobs_queue.grant_send_messages(function)
        gpu_jobs_queue.grant_send_messages(function)
        hf_token_key.grant_encrypt_decrypt(function)

        integration = apigwv2_integrations.HttpLambdaIntegration("ApiIntegration", function)
        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name=f"modelforge-api-{env_name}",
            create_default_stage=True,
        )
        http_api.add_routes(
            path="/{proxy+}", methods=[apigwv2.HttpMethod.ANY], integration=integration
        )
        http_api.add_routes(
            path="/", methods=[apigwv2.HttpMethod.ANY], integration=integration
        )

        self.function = function
        self.http_api = http_api

        CfnOutput(self, "ApiUrl", value=http_api.api_endpoint)
        CfnOutput(self, "ApiFunctionName", value=function.function_name)
