"""ComputeStack: Fargate Spot compute environment + cpu/gpu Batch job definitions, and the
dispatcher Lambda that submits to them, triggered by cpu-jobs/gpu-jobs SQS.

Written and `cdk synth`-tested this round; not deployed. Worker container images
(cpu-base/gpu-base) aren't built/pushed yet (Day 11+), so job definitions reference a
placeholder public image — swap for a real ECR URI once those images exist.

Cost: Fargate Spot only (no EC2/on-demand compute environment), no NAT gateway (public
subnets + `assign_public_ip`, since worker tasks only need outbound S3/DynamoDB/SQS
access, not inbound) — see docs/COSTS.md's "nothing always-on" rule. A Batch compute
environment and job queue cost nothing by themselves; cost only starts when a job runs.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import Duration, Size, Stack
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_sqs as sqs
from constructs import Construct

# No CDK-managed DynamoDB table exists yet (Day 10's table is LocalStack-only, created by
# infra/localstack/init-aws.sh) — the real table is a Day 19/20 gap. IAM policies here are
# scoped to this fixed table name so they're still least-privilege once that stack lands,
# rather than granted access to "*".
_JOBS_TABLE_NAME = "modelforge"
_WORKER_IMAGES = ("cpu-base", "gpu-base")
_PLACEHOLDER_IMAGE = "public.ecr.aws/docker/library/busybox:latest"


def _table_arn(stack: Stack) -> str:
    return (
        f"arn:aws:dynamodb:{stack.region}:{stack.account}:table/{_JOBS_TABLE_NAME}"
    )


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        uploads_bucket_arn: str,
        results_bucket_arn: str,
        cpu_jobs_queue: sqs.IQueue,
        gpu_jobs_queue: sqs.IQueue,
        dispatcher_code_path: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "WorkerVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                )
            ],
        )

        compute_environment = batch.FargateComputeEnvironment(
            self,
            "WorkerComputeEnvironment",
            vpc=vpc,
            spot=True,
            compute_environment_name="modelforge-worker-compute-dev",
        )

        job_queue = batch.JobQueue(
            self,
            "WorkerJobQueue",
            job_queue_name="modelforge-worker-queue-dev",
            compute_environments=[
                batch.OrderedComputeEnvironment(
                    compute_environment=compute_environment, order=1
                )
            ],
        )

        job_role = iam.Role(
            self,
            "WorkerJobRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        job_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject"],
                resources=[f"{uploads_bucket_arn}/*", f"{results_bucket_arn}/*"],
            )
        )
        job_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                ],
                resources=[_table_arn(self), f"{_table_arn(self)}/index/*"],
            )
        )

        self.job_definitions: dict[str, batch.EcsJobDefinition] = {}
        for worker_image in _WORKER_IMAGES:
            container = batch.EcsFargateContainerDefinition(
                self,
                f"{worker_image.title().replace('-', '')}Container",
                image=ecs.ContainerImage.from_registry(_PLACEHOLDER_IMAGE),
                cpu=1,
                memory=Size.gibibytes(2),
                job_role=job_role,
                command=["python", "-m", "core.runner"],
            )
            self.job_definitions[worker_image] = batch.EcsJobDefinition(
                self,
                f"{worker_image.title().replace('-', '')}JobDefinition",
                container=container,
                job_definition_name=f"{worker_image}-job-def-dev",
                timeout=Duration.hours(2),
            )

        dispatcher_role = iam.Role(
            self,
            "DispatcherRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        dispatcher_role.add_to_policy(
            iam.PolicyStatement(
                actions=["batch:SubmitJob", "batch:TerminateJob"],
                resources=[job_queue.job_queue_arn]
                + [jd.job_definition_arn for jd in self.job_definitions.values()],
            )
        )
        dispatcher_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:UpdateItem"],
                resources=[_table_arn(self)],
            )
        )

        self.dispatcher = lambda_.Function(
            self,
            "DispatcherFunction",
            function_name="modelforge-dispatcher-dev",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="dispatcher.handler.handler",
            code=lambda_.Code.from_asset(dispatcher_code_path),
            role=dispatcher_role,
            timeout=Duration.seconds(30),
            environment={"MF_BATCH_CLIENT": "real"},
        )
        self.dispatcher.add_event_source(
            lambda_events.SqsEventSource(cpu_jobs_queue, batch_size=1)
        )
        self.dispatcher.add_event_source(
            lambda_events.SqsEventSource(gpu_jobs_queue, batch_size=1)
        )
