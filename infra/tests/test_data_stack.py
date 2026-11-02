"""DataStack synth tests — offline, no deploy."""

from __future__ import annotations

from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from stacks.data_stack import DataStack


def _synth_template() -> Template:
    app = App()
    stack = DataStack(
        app,
        "TestDataStack",
        env_name="dev",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


def test_table_has_gsi1_and_ttl():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        Match.object_like(
            {
                "GlobalSecondaryIndexes": Match.array_with(
                    [Match.object_like({"IndexName": "GSI1"})]
                ),
                "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
                "BillingMode": "PAY_PER_REQUEST",
            }
        ),
    )


def test_table_pitr_off_in_dev():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        Match.object_like(
            {"PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": False}}
        ),
    )


def test_buckets_block_public_access():
    template = _synth_template()
    buckets = template.find_resources("AWS::S3::Bucket")
    assert len(buckets) == 2
    for bucket in buckets.values():
        config = bucket["Properties"]["PublicAccessBlockConfiguration"]
        assert config["BlockPublicAcls"] is True
        assert config["BlockPublicPolicy"] is True


def test_queues_have_dead_letter_queues():
    template = _synth_template()
    template.resource_count_is("AWS::SQS::Queue", 6)  # 3 queues + 3 DLQs
