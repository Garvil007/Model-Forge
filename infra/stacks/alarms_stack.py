"""AlarmsStack: dead-letter-queue depth alarms, Lambda error alarms, and an AWS Budgets
alarm at $20/month.

No SNS topic/action is wired to the CloudWatch alarms — this is a solo dev environment
with no on-call, so an alarm firing with no subscriber is a conscious choice, not an
oversight: check the AWS console/CLI when something looks wrong rather than paging
anyone. The Budget notification is the one alert that does email someone, since AWS
Budgets requires a `NotificationWithSubscribers` to mean anything at all.

Cost: CloudWatch alarms are ~$0.10/month each; AWS Budgets' first budget report is free.
See docs/COSTS.md.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import Duration, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sqs as sqs
from constructs import Construct

_BUDGET_LIMIT_USD = 20
_DLQ_DEPTH_THRESHOLD = 1


class AlarmsStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        cpu_jobs_dlq: sqs.IQueue,
        gpu_jobs_dlq: sqs.IQueue,
        system_jobs_dlq: sqs.IQueue,
        dispatcher_function: lambda_.IFunction,
        api_function: lambda_.IFunction,
        budget_notification_email: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for name, dlq in (
            ("CpuJobsDlq", cpu_jobs_dlq),
            ("GpuJobsDlq", gpu_jobs_dlq),
            ("SystemJobsDlq", system_jobs_dlq),
        ):
            cloudwatch.Alarm(
                self,
                f"{name}DepthAlarm",
                alarm_name=f"modelforge-{dlq.queue_name}-depth-{env_name}",
                alarm_description=(
                    f"{dlq.queue_name} has a message: a job failed all 3 delivery "
                    "attempts and needs manual investigation."
                ),
                metric=dlq.metric_approximate_number_of_messages_visible(
                    period=Duration.minutes(5), statistic="Maximum"
                ),
                threshold=_DLQ_DEPTH_THRESHOLD,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            )

        for name, fn in (("Dispatcher", dispatcher_function), ("Api", api_function)):
            cloudwatch.Alarm(
                self,
                f"{name}ErrorsAlarm",
                alarm_name=f"modelforge-{name.lower()}-errors-{env_name}",
                alarm_description=f"{name} Lambda is throwing errors.",
                metric=fn.metric_errors(period=Duration.minutes(5), statistic="Sum"),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            )

        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=_BUDGET_LIMIT_USD, unit="USD"
                ),
                budget_name=f"modelforge-{env_name}-monthly",
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=threshold_percent,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL",
                            address=budget_notification_email,
                        )
                    ],
                )
                for threshold_percent in (80, 100)
            ],
        )
