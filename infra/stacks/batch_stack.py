"""BatchStack: Fargate Spot compute environment, one Batch job queue per op queue
("cpu"/"gpu", matching `packages/catalog`'s `Queue` literal), one job definition per real
worker image, ECR repos (lifecycle: keep only the last 3 images) for each, and the
dispatcher Lambda that submits to them, triggered by cpu-jobs/gpu-jobs SQS.

Renamed from Day 10's `ComputeStack`. Fixes two real dispatch bugs found while deploying
this stack:

1. `infra/lambda/dispatcher/dispatcher/handler.py` submits to a job queue named
   literally `f"{operation.queue}-queue"` (`cpu-queue`/`gpu-queue`) and a job definition
   named literally `f"{worker_image}-job-def"` — the old stack created one shared queue
   named `modelforge-worker-queue-dev` and job defs suffixed `-dev`, so a real dispatch
   would have failed to find either resource.
2. The dispatcher Lambda's code asset was a plain `Code.from_asset("lambda/dispatcher")`
   — only its own `dispatcher/` package, with `modelforge_catalog`/`modelforge_db`
   (editable-only, not on PyPI) never bundled in. Every real invocation crashed at
   import time (`Runtime.ImportModuleError: No module named 'modelforge_catalog'`),
   confirmed live in CloudWatch Logs. Bundled via a Docker-based `pip install --no-deps`
   step (mirrors how `ApiStack`'s container image bundles the same two packages) rather
   than a container image, since this Lambda's only dependency beyond them is `boto3`,
   already provided by the Lambda runtime.

Also replaces the Day 10/11 `cpu-base`/`gpu-base` busybox placeholders with the real
per-image set built in `workers/images/` (`cpu-torch`, `cpu-tf`, `cpu-convert`,
`cpu-llm`, `gpu-base`, `tensorrt`).

Cost: Fargate Spot only (no EC2/on-demand compute environment, min 0 vCPUs), no NAT
gateway (NetworkStack's public subnets + `assign_public_ip`, since worker tasks only need
outbound S3/DynamoDB/SQS/ECR access, not inbound) — see docs/COSTS.md's "nothing
always-on" rule. A Batch compute environment, job queue and ECR repo cost nothing by
themselves; cost only starts when a job runs or an image is stored.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import BundlingOptions, Duration, RemovalPolicy, Size, Stack
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_sqs as sqs
from constructs import Construct

_WORKER_IMAGES = ("cpu-torch", "cpu-tf", "cpu-convert", "cpu-llm", "gpu-base", "tensorrt")
_QUEUES = ("cpu", "gpu")


def _construct_name(worker_image: str) -> str:
    return worker_image.title().replace("-", "")


class BatchStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        vpc: ec2.IVpc,
        worker_security_group: ec2.ISecurityGroup,
        uploads_bucket_arn: str,
        uploads_bucket_name: str,
        results_bucket_arn: str,
        results_bucket_name: str,
        table_arn: str,
        cpu_jobs_queue: sqs.IQueue,
        gpu_jobs_queue: sqs.IQueue,
        dispatcher_code_path: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        is_dev = env_name == "dev"

        compute_environment = batch.FargateComputeEnvironment(
            self,
            "WorkerComputeEnvironment",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[worker_security_group],
            spot=True,
            compute_environment_name=f"modelforge-worker-compute-{env_name}",
        )

        self.job_queues: dict[str, batch.JobQueue] = {
            q: batch.JobQueue(
                self,
                f"{q.title()}JobQueue",
                job_queue_name=f"{q}-queue",
                compute_environments=[
                    batch.OrderedComputeEnvironment(
                        compute_environment=compute_environment, order=1
                    )
                ],
            )
            for q in _QUEUES
        }

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
                resources=[table_arn, f"{table_arn}/index/*"],
            )
        )

        self.ecr_repositories: dict[str, ecr.Repository] = {}
        self.job_definitions: dict[str, batch.EcsJobDefinition] = {}
        for worker_image in _WORKER_IMAGES:
            name = _construct_name(worker_image)
            repo = ecr.Repository(
                self,
                f"{name}Repository",
                repository_name=f"modelforge-{worker_image}",
                image_scan_on_push=True,
                removal_policy=RemovalPolicy.DESTROY if is_dev else RemovalPolicy.RETAIN,
                empty_on_delete=is_dev,
                lifecycle_rules=[
                    ecr.LifecycleRule(
                        description="keep only the last 3 images",
                        max_image_count=3,
                        rule_priority=1,
                    )
                ],
            )
            self.ecr_repositories[worker_image] = repo

            container = batch.EcsFargateContainerDefinition(
                self,
                f"{name}Container",
                image=ecs.ContainerImage.from_ecr_repository(repo, "latest"),
                cpu=1,
                memory=Size.gibibytes(2),
                job_role=job_role,
                # Ref::message resolves from the SubmitJob-time `message` parameter
                # the dispatcher sends (see batch_client.RealBatchJobClient.submit_job)
                # — the real SQS message body telling this one-shot container which
                # job to run (core/runner.py's sys.argv[1] one-shot branch). Must be
                # in `command`, not `environment`: confirmed live that AWS Batch only
                # resolves `Ref::` placeholders in the command array — as an
                # environment variable value it arrived as the literal unsubstituted
                # string "Ref::message". And it must be ONLY the message, not
                # ["python", "-m", "core.runner", "Ref::message"]: every worker
                # Dockerfile already sets `ENTRYPOINT ["python", "-m", "core.runner"]`,
                # and ECS appends `command` to `ENTRYPOINT` rather than replacing it —
                # confirmed live that the actual argv became
                # ["python", "-m", "core.runner", "python", "-m", "core.runner", "<msg>"],
                # so sys.argv[1] was the literal string "python", not the message.
                command=["Ref::message"],
                # Confirmed live: every `workers/ops/*.py` module reads
                # MF_UPLOADS_BUCKET/MF_RESULTS_BUCKET via `os.environ.get(..., "mf-uploads"/
                # "mf-results")` (the LocalStack dev bucket names) — without these set, a
                # real job's download/upload hit a bucket that doesn't exist in this AWS
                # account at all, surfacing as a confusing "403 Forbidden" HeadObject error
                # (S3 masks "no such bucket" as 403 rather than 404 when the caller has no
                # permission on that bucket name either) rather than a clear "bucket not
                # found".
                environment={
                    "MF_UPLOADS_BUCKET": uploads_bucket_name,
                    "MF_RESULTS_BUCKET": results_bucket_name,
                    "MF_AWS_REGION": self.region,
                },
                # Required: these tasks run in NetworkStack's public-only subnets with no
                # NAT gateway (see docs/decisions.md). `assign_public_ip` defaults to False
                # on this construct regardless of subnet type, which left the first real
                # job here unable to even pull its own image — confirmed live via a real
                # Batch FAILED job: "ResourceInitializationError: unable to pull secrets
                # or registry auth: ... dial tcp ...: i/o timeout" reaching ECR.
                assign_public_ip=True,
            )
            self.job_definitions[worker_image] = batch.EcsJobDefinition(
                self,
                f"{name}JobDefinition",
                container=container,
                job_definition_name=f"{worker_image}-job-def",
                # A default so `Ref::message` has something to resolve to even if a
                # job is ever submitted without the SubmitJob-time override (it would
                # then cleanly hit the "exactly one of ..." error in core/runner.py
                # rather than Batch rejecting the submission outright).
                parameters={"message": ""},
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
        # The dispatcher calls SubmitJob with the job definition *name* (no revision),
        # not an ARN (see dispatcher/handler.py's `_job_definition_for`). AWS Batch
        # authorizes a by-name SubmitJob against the unrevisioned family ARN
        # ("job-definition/<name>", no ":<revision>" suffix) — confirmed live via a real
        # AccessDeniedException whose resource had no revision suffix, even though
        # `EcsJobDefinition.job_definition_arn` returns the ":1"-revisioned ARN. A
        # trailing wildcard covers both forms rather than relying on exactly matching
        # whichever one Batch happens to check.
        job_definition_resources = [
            f"arn:aws:batch:{self.region}:{self.account}:job-definition/{worker_image}-job-def*"
            for worker_image in _WORKER_IMAGES
        ]
        dispatcher_role.add_to_policy(
            iam.PolicyStatement(
                actions=["batch:SubmitJob", "batch:TerminateJob"],
                resources=[jq.job_queue_arn for jq in self.job_queues.values()]
                + job_definition_resources,
            )
        )
        dispatcher_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:UpdateItem"],
                resources=[table_arn],
            )
        )

        self.dispatcher = lambda_.Function(
            self,
            "DispatcherFunction",
            function_name=f"modelforge-dispatcher-{env_name}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="dispatcher.handler.handler",
            code=lambda_.Code.from_asset(
                dispatcher_code_path,
                exclude=[
                    ".git",
                    ".github",
                    ".claude",
                    ".ruff_cache",
                    "**/__pycache__",
                    "**/.pytest_cache",
                    "**/*.egg-info",
                    "apps",
                    "workers",
                    "docs",
                    "infra/cdk.out",
                ],
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir --no-deps "
                        "packages/catalog packages/db infra/lambda/dispatcher "
                        "-t /asset-output",
                    ],
                ),
            ),
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
