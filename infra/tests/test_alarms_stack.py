"""AlarmsStack synth tests — offline, no deploy."""

from __future__ import annotations

from aws_cdk import App, Environment, Stack
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sqs as sqs
from aws_cdk.assertions import Match, Template

from stacks.alarms_stack import AlarmsStack

_ENV = Environment(account="123456789012", region="us-east-1")


def _synth_template() -> Template:
    app = App()
    helper = Stack(app, "HelperStackForAlarms", env=_ENV)
    cpu_dlq = sqs.Queue(helper, "CpuDlq")
    gpu_dlq = sqs.Queue(helper, "GpuDlq")
    system_dlq = sqs.Queue(helper, "SystemDlq")
    dispatcher_fn = lambda_.Function(
        helper,
        "DispatcherFn",
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="x.handler",
        code=lambda_.Code.from_inline("def handler(event, context): return {}"),
    )
    api_fn = lambda_.Function(
        helper,
        "ApiFn",
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="x.handler",
        code=lambda_.Code.from_inline("def handler(event, context): return {}"),
    )

    stack = AlarmsStack(
        app,
        "TestAlarmsStack",
        env_name="dev",
        cpu_jobs_dlq=cpu_dlq,
        gpu_jobs_dlq=gpu_dlq,
        system_jobs_dlq=system_dlq,
        dispatcher_function=dispatcher_fn,
        api_function=api_fn,
        budget_notification_email="test@example.com",
        env=_ENV,
    )
    return Template.from_stack(stack)


def test_budget_exists_with_twenty_dollar_limit():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        Match.object_like(
            {
                "Budget": Match.object_like(
                    {
                        "BudgetLimit": {"Amount": 20, "Unit": "USD"},
                        "BudgetType": "COST",
                        "TimeUnit": "MONTHLY",
                    }
                )
            }
        ),
    )


def test_dlq_depth_alarms_exist():
    template = _synth_template()
    template.resource_count_is("AWS::CloudWatch::Alarm", 5)  # 3 DLQ + 2 Lambda error alarms
