"""NetworkStack synth tests — offline, no deploy."""

from __future__ import annotations

from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from stacks.network_stack import NetworkStack


def _synth_template() -> Template:
    app = App()
    stack = NetworkStack(
        app, "TestNetworkStack", env=Environment(account="123456789012", region="us-east-1")
    )
    return Template.from_stack(stack)


def test_no_nat_gateway():
    template = _synth_template()
    template.resource_count_is("AWS::EC2::NatGateway", 0)


def test_public_subnets_exist():
    template = _synth_template()
    subnets = template.find_resources(
        "AWS::EC2::Subnet", {"Properties": Match.object_like({"MapPublicIpOnLaunch": True})}
    )
    assert len(subnets) >= 2


def test_worker_security_group_has_no_ingress():
    template = _synth_template()
    groups = template.find_resources("AWS::EC2::SecurityGroup")
    assert len(groups) >= 1
    for group in groups.values():
        assert group["Properties"].get("SecurityGroupIngress", []) == []
