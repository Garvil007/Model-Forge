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

from aws_cdk import BundlingOptions, Duration, RemovalPolicy, Size, Stack, Tags
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct

_WORKER_IMAGES = ("cpu-torch", "cpu-tf", "cpu-convert", "cpu-llm", "gpu-base", "tensorrt")
_GPU_WORKER_IMAGES = ("gpu-base", "tensorrt")
_QUEUES = ("cpu", "gpu")
# g6.xlarge/g5.xlarge: 4 vCPU, 1 GPU each. maxv_cpus=4 caps the GPU compute environment at
# one instance at a time — matches the account's requested G/VT Spot quota (see
# docs/decisions.md's "Day 20" entry). Raise alongside an actual quota increase, not before.
_GPU_INSTANCE_TYPES = [ec2.InstanceType("g6.xlarge"), ec2.InstanceType("g5.xlarge")]
_GPU_MAX_VCPUS = 4
_GPU_CONTAINER_VCPUS = 4
_GPU_CONTAINER_MEMORY = Size.gibibytes(14)  # leaves headroom under the 16 GiB instance for ECS


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
        gpu_on_demand_fallback_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        is_dev = env_name == "dev"

        # No cost-allocation tags on this one: AWS::Batch::ComputeEnvironment doesn't
        # support in-place tag updates, and this resource has a fixed
        # `compute_environment_name` — CloudFormation refuses to replace a
        # custom-named resource in an update ("Rename ... and update the stack again"),
        # confirmed live. Safe to skip: it's the only queue on this CE, so Cost
        # Explorer's service-level breakdown already identifies its spend as Batch/EC2
        # Fargate without needing the tag.
        compute_environment = batch.FargateComputeEnvironment(
            self,
            "WorkerComputeEnvironment",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[worker_security_group],
            spot=True,
            compute_environment_name=f"modelforge-worker-compute-{env_name}",
        )

        # GPU jobs need an EC2 (not Fargate) compute environment — Fargate has no GPU
        # support. Spot is the primary (and only enabled-by-default) path; an on-demand
        # fallback compute environment can be added at lower priority (order=2), but
        # only when explicitly turned on — AWS Batch requires a compute environment to
        # be *created* in ENABLED state (confirmed live: `enabled=False` at creation is
        # rejected with "Compute Environment must be created in ENABLED state"), so
        # "disabled by default" means this resource isn't created at all until asked
        # for, not that it exists sitting disabled. This also means a Spot capacity
        # shortage degrades to "GPU jobs wait" rather than silently falling back to
        # on-demand pricing (~3x the Spot price) without anyone asking for that.
        gpu_spot_compute_environment = batch.ManagedEc2EcsComputeEnvironment(
            self,
            "GpuSpotComputeEnvironment",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[worker_security_group],
            instance_types=_GPU_INSTANCE_TYPES,
            use_optimal_instance_classes=False,
            spot=True,
            minv_cpus=0,
            maxv_cpus=_GPU_MAX_VCPUS,
            compute_environment_name=f"modelforge-gpu-spot-compute-{env_name}",
        )
        Tags.of(gpu_spot_compute_environment).add("mf:queue", "gpu")
        Tags.of(gpu_spot_compute_environment).add("mf:project", "modelforge")

        gpu_compute_environment_orders = [
            batch.OrderedComputeEnvironment(
                compute_environment=gpu_spot_compute_environment, order=1
            )
        ]
        if gpu_on_demand_fallback_enabled:
            gpu_on_demand_compute_environment = batch.ManagedEc2EcsComputeEnvironment(
                self,
                "GpuOnDemandComputeEnvironment",
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
                security_groups=[worker_security_group],
                instance_types=_GPU_INSTANCE_TYPES,
                use_optimal_instance_classes=False,
                spot=False,
                minv_cpus=0,
                maxv_cpus=_GPU_MAX_VCPUS,
                compute_environment_name=f"modelforge-gpu-ondemand-compute-{env_name}",
            )
            Tags.of(gpu_on_demand_compute_environment).add("mf:queue", "gpu")
            Tags.of(gpu_on_demand_compute_environment).add("mf:project", "modelforge")
            gpu_compute_environment_orders.append(
                batch.OrderedComputeEnvironment(
                    compute_environment=gpu_on_demand_compute_environment, order=2
                )
            )

        self.job_queues: dict[str, batch.JobQueue] = {
            "cpu": batch.JobQueue(
                self,
                "CpuJobQueue",
                job_queue_name="cpu-queue",
                compute_environments=[
                    batch.OrderedComputeEnvironment(
                        compute_environment=compute_environment, order=1
                    )
                ],
            ),
            "gpu": batch.JobQueue(
                self,
                "GpuJobQueue",
                job_queue_name="gpu-queue",
                compute_environments=gpu_compute_environment_orders,
            ),
        }

        self.gpu_kill_switch = ssm.StringParameter(
            self,
            "GpuKillSwitch",
            parameter_name=f"/modelforge/{env_name}/gpu-kill-switch",
            string_value="off",
            description=(
                "Set to 'on' to stop new GPU jobs being queued (checked by POST /jobs and "
                "the dispatcher). See modelforge_db.kill_switch."
            ),
        )

        job_role = iam.Role(
            self,
            "WorkerJobRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        # Least privilege by direction, not just by bucket: every worker op only ever
        # downloads from `uploads_bucket` and uploads to `results_bucket` (see
        # `workers/ops/_convert_common.py::_run_in_tempdir`'s `s3.download_file`/
        # `s3.upload_file` calls) — it never needs to overwrite another user's upload or
        # read another user's already-produced result. Splitting the actions removes
        # both of those unused, unnecessarily broad grants. This role is still shared by
        # every job on this job definition (static at Batch job-definition deploy time,
        # not per-SubmitJob), so it is NOT scoped to a single job's own S3 prefix — true
        # per-job scoping would need the dispatcher to mint per-job scoped credentials
        # (e.g. an STS AssumeRole session policy keyed on job/user id) at SubmitJob time,
        # which is a real architecture change, not a policy tweak; tracked as residual
        # risk rather than done here.
        job_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"{uploads_bucket_arn}/*"],
            )
        )
        job_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{results_bucket_arn}/*"],
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

            # `Ref::message` resolves from the SubmitJob-time `message` parameter the
            # dispatcher sends (see batch_client.RealBatchJobClient.submit_job) — the
            # real SQS message body telling this one-shot container which job to run
            # (core/runner.py's sys.argv[1] one-shot branch). Must be in `command`, not
            # `environment`: confirmed live that AWS Batch only resolves `Ref::`
            # placeholders in the command array — as an environment variable value it
            # arrived as the literal unsubstituted string "Ref::message". And it must be
            # ONLY the message, not ["python", "-m", "core.runner", "Ref::message"]:
            # every worker Dockerfile already sets
            # `ENTRYPOINT ["python", "-m", "core.runner"]`, and ECS appends `command` to
            # `ENTRYPOINT` rather than replacing it — confirmed live that the actual argv
            # became ["python", "-m", "core.runner", "python", "-m", "core.runner",
            # "<msg>"], so sys.argv[1] was the literal string "python", not the message.
            # Confirmed live: every `workers/ops/*.py` module reads
            # MF_UPLOADS_BUCKET/MF_RESULTS_BUCKET via `os.environ.get(..., "mf-uploads"/
            # "mf-results")` (the LocalStack dev bucket names) — without these set, a
            # real job's download/upload hit a bucket that doesn't exist in this AWS
            # account at all, surfacing as a confusing "403 Forbidden" HeadObject error
            # (S3 masks "no such bucket" as 403 rather than 404 when the caller has no
            # permission on that bucket name either) rather than a clear "bucket not
            # found".
            shared_container_kwargs: dict[str, Any] = {
                "image": ecs.ContainerImage.from_ecr_repository(repo, "latest"),
                "job_role": job_role,
                "command": ["Ref::message"],
                "environment": {
                    "MF_UPLOADS_BUCKET": uploads_bucket_name,
                    "MF_RESULTS_BUCKET": results_bucket_name,
                    "MF_AWS_REGION": self.region,
                },
            }
            if worker_image in _GPU_WORKER_IMAGES:
                # GPU jobs run on the EC2 compute environments above — Fargate has no
                # GPU support. `gpu=1` reserves the instance's one GPU for this
                # container; `assign_public_ip` doesn't apply to EC2 launch type (the
                # instance itself gets a public IP from the public subnet, same as the
                # Fargate tasks below).
                container = batch.EcsEc2ContainerDefinition(
                    self,
                    f"{name}Container",
                    cpu=_GPU_CONTAINER_VCPUS,
                    memory=_GPU_CONTAINER_MEMORY,
                    gpu=1,
                    **shared_container_kwargs,
                )
            else:
                container = batch.EcsFargateContainerDefinition(
                    self,
                    f"{name}Container",
                    cpu=1,
                    memory=Size.gibibytes(2),
                    # Required: these tasks run in NetworkStack's public-only subnets
                    # with no NAT gateway (see docs/decisions.md). `assign_public_ip`
                    # defaults to False on this construct regardless of subnet type,
                    # which left the first real job here unable to even pull its own
                    # image — confirmed live via a real Batch FAILED job:
                    # "ResourceInitializationError: unable to pull secrets or registry
                    # auth: ... dial tcp ...: i/o timeout" reaching ECR.
                    assign_public_ip=True,
                    **shared_container_kwargs,
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
        self.gpu_kill_switch.grant_read(dispatcher_role)

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
            environment={"MF_BATCH_CLIENT": "real", "MF_ENV_NAME": env_name},
        )
        self.dispatcher.add_event_source(
            lambda_events.SqsEventSource(cpu_jobs_queue, batch_size=1)
        )
        self.dispatcher.add_event_source(
            lambda_events.SqsEventSource(gpu_jobs_queue, batch_size=1)
        )

        cost_recorder_role = iam.Role(
            self,
            "CostRecorderRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        cost_recorder_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
                resources=[table_arn],
            )
        )

        self.cost_recorder = lambda_.Function(
            self,
            "CostRecorderFunction",
            function_name=f"modelforge-cost-recorder-{env_name}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="cost_recorder.handler.handler",
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
                        "packages/catalog packages/db infra/lambda/cost_recorder "
                        "-t /asset-output",
                    ],
                ),
            ),
            role=cost_recorder_role,
            timeout=Duration.seconds(30),
        )
        # Batch's own "Job State Change" events — fired for every job in this account,
        # so the rule filters to this stack's two queues and the terminal statuses the
        # handler actually acts on (see cost_recorder/handler.py's docstring for why the
        # job/user id come from `detail.parameters.message`, not the event's `jobName`).
        events.Rule(
            self,
            "BatchJobStateChangeRule",
            event_pattern=events.EventPattern(
                source=["aws.batch"],
                detail_type=["Batch Job State Change"],
                detail={
                    "status": ["SUCCEEDED", "FAILED"],
                    "jobQueue": [jq.job_queue_arn for jq in self.job_queues.values()],
                },
            ),
            targets=[events_targets.LambdaFunction(self.cost_recorder)],
        )
