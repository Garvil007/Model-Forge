"""BatchStack synth tests — offline, no deploy.

Covers the dispatch-naming fix: job queues must be literally `cpu-queue`/`gpu-queue` and
job definitions literally `{worker_image}-job-def`, matching
`infra/lambda/dispatcher/dispatcher/handler.py`'s hardcoded lookup.
"""

from __future__ import annotations

from aws_cdk import App, Environment, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_sqs as sqs
from aws_cdk.assertions import Match, Template

from stacks.batch_stack import BatchStack

_ENV = Environment(account="123456789012", region="us-east-1")


def _synth_template() -> Template:
    app = App()
    helper = Stack(app, "HelperStack", env=_ENV)
    vpc = ec2.Vpc(helper, "Vpc", max_azs=2, nat_gateways=0)
    sg = ec2.SecurityGroup(helper, "Sg", vpc=vpc)
    cpu_queue = sqs.Queue(helper, "CpuQueue")
    gpu_queue = sqs.Queue(helper, "GpuQueue")

    stack = BatchStack(
        app,
        "TestBatchStack",
        env_name="dev",
        vpc=vpc,
        worker_security_group=sg,
        uploads_bucket_arn="arn:aws:s3:::test-uploads",
        uploads_bucket_name="test-uploads",
        results_bucket_arn="arn:aws:s3:::test-results",
        results_bucket_name="test-results",
        table_arn="arn:aws:dynamodb:us-east-1:123456789012:table/modelforge",
        cpu_jobs_queue=cpu_queue,
        gpu_jobs_queue=gpu_queue,
        dispatcher_code_path="..",
        env=_ENV,
    )
    return Template.from_stack(stack)


def test_fargate_spot_compute_environment_exists():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {"ComputeResources": Match.object_like({"Type": "FARGATE_SPOT"})},
    )


def test_gpu_spot_compute_environment_capped_at_quota():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        Match.object_like(
            {
                "ComputeResources": Match.object_like(
                    {
                        "Type": "SPOT",
                        "MaxvCpus": 4,
                        "MinvCpus": 0,
                        "InstanceTypes": Match.array_with(["g6.xlarge", "g5.xlarge"]),
                    }
                )
            }
        ),
    )


def test_gpu_on_demand_fallback_not_created_by_default():
    # AWS Batch requires a compute environment to be created ENABLED (confirmed live),
    # so "disabled by default" means the on-demand fallback CE doesn't exist at all
    # until `gpu_on_demand_fallback_enabled=True` is passed — not that it exists sitting
    # disabled. Only the GPU Spot compute environment should exist by default.
    template = _synth_template()
    gpu_ec2_compute_environments = template.find_resources(
        "AWS::Batch::ComputeEnvironment",
        {"Properties": {"ComputeResources": Match.object_like({"Type": "SPOT"})}},
    )
    assert len(gpu_ec2_compute_environments) == 1


def test_gpu_job_definitions_reserve_a_gpu():
    template = _synth_template()
    for image in ("gpu-base", "tensorrt"):
        template.has_resource_properties(
            "AWS::Batch::JobDefinition",
            Match.object_like(
                {
                    "JobDefinitionName": f"{image}-job-def",
                    "ContainerProperties": Match.object_like(
                        {
                            "ResourceRequirements": Match.array_with(
                                [{"Type": "GPU", "Value": "1"}]
                            )
                        }
                    ),
                }
            ),
        )


def test_gpu_kill_switch_parameter_exists():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/modelforge/dev/gpu-kill-switch", "Value": "off"},
    )


def test_job_queues_named_for_dispatcher():
    template = _synth_template()
    template.has_resource_properties("AWS::Batch::JobQueue", {"JobQueueName": "cpu-queue"})
    template.has_resource_properties("AWS::Batch::JobQueue", {"JobQueueName": "gpu-queue"})
    template.resource_count_is("AWS::Batch::JobQueue", 2)


def test_job_definitions_named_for_dispatcher():
    template = _synth_template()
    template.resource_count_is("AWS::Batch::JobDefinition", 6)
    for image in ("cpu-torch", "cpu-tf", "cpu-convert", "cpu-llm", "gpu-base", "tensorrt"):
        template.has_resource_properties(
            "AWS::Batch::JobDefinition", {"JobDefinitionName": f"{image}-job-def"}
        )


def test_ecr_repositories_keep_last_three_images():
    template = _synth_template()
    repos = template.find_resources("AWS::ECR::Repository")
    assert len(repos) == 6
    for repo in repos.values():
        rules = repo["Properties"]["LifecyclePolicy"]["LifecyclePolicyText"]
        assert '"countNumber":3' in rules.replace(" ", "")


def test_dispatcher_lambda_and_sqs_triggers_exist():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like({"Handler": "dispatcher.handler.handler"}),
    )
    template.resource_count_is("AWS::Lambda::EventSourceMapping", 2)


def test_iam_policies_scope_sensitive_actions_not_wildcard_resource():
    template = _synth_template()
    policies = template.find_resources("AWS::IAM::Policy")
    for policy in policies.values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            actions = statement["Action"]
            actions = actions if isinstance(actions, list) else [actions]
            sensitive = any(
                a.startswith("batch:") or a.startswith("dynamodb:") or a.startswith("s3:")
                for a in actions
            )
            if sensitive:
                resources = statement["Resource"]
                resources = resources if isinstance(resources, list) else [resources]
                assert "*" not in resources
