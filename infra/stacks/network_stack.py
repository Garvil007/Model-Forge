"""NetworkStack: a VPC with public subnets only, no NAT gateway.

Cost: a NAT gateway is ~$0.045/hour (~$33/month) plus per-GB data processing — always-on
spend for a dev environment that may run zero jobs some days. Worker tasks (BatchStack)
only need outbound access to S3/DynamoDB/SQS/ECR, never inbound, so they run with a
public IP (`assign_public_ip=True` on the Fargate job) and a security group with no
ingress rules at all — outbound-only. See docs/decisions.md ("Day 19: public subnets,
no NAT gateway") for the full trade-off.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                )
            ],
        )

        self.worker_security_group = ec2.SecurityGroup(
            self,
            "WorkerSecurityGroup",
            vpc=self.vpc,
            description="ModelForge Batch workers: outbound-only, no inbound rules",
            allow_all_outbound=True,
        )
