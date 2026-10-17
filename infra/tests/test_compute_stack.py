"""ComputeStack synth tests — offline, no deploy."""

from __future__ import annotations

from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from stacks.compute_stack import ComputeStack


def _synth_template() -> Template:
    app = App()
    stack = ComputeStack(
        app,
        "TestComputeStack",
        uploads_bucket_arn="arn:aws:s3:::test-uploads",
        results_bucket_arn="arn:aws:s3:::test-results",
        cpu_jobs_queue=_fake_queue(app, "CpuQueue"),
        gpu_jobs_queue=_fake_queue(app, "GpuQueue"),
        dispatcher_code_path="lambda/dispatcher",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


def _fake_queue(app, construct_id):
    from aws_cdk import Stack
    from aws_cdk import aws_sqs as sqs

    helper_stack = Stack(app, f"{construct_id}HelperStack", env=Environment(
        account="123456789012", region="us-east-1"
    ))
    return sqs.Queue(helper_stack, construct_id)


def test_fargate_spot_compute_environment_exists():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {"ComputeResources": Match.object_like({"Type": "FARGATE_SPOT"})},
    )


def test_both_job_definitions_exist():
    template = _synth_template()
    template.resource_count_is("AWS::Batch::JobDefinition", 2)


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
