"""GithubOidcStack: GitHub Actions OIDC identity provider and a least-privilege deploy
role, so CI can `cdk deploy` and push images/assets without any long-lived AWS access
keys stored as GitHub secrets.

One AWS account is assumed per environment (dev and prod are separate accounts) — that's
what makes it safe for both environments' pipelines to each create their own copy of this
stack: the OIDC provider is a singleton *per account*, not per CDK app, so there is never a
collision. If dev and prod ever shared one account, only one of the two `cdk deploy`s for
this stack should run; see docs/decisions.md ("GitHub OIDC trust boundary").

The role trusts only this repo, and only the ref this environment is meant to deploy from:
dev trusts pushes to `refs/heads/main`, prod trusts the GitHub Environment named
"production" (so prod deploys require whatever required reviewers that Environment has
configured in the GitHub repo settings — this stack does not and cannot configure GitHub
Environments itself).

Permissions granted (all read the "why" in the comments below, not just the "what"):
  - sts:AssumeRole on the three CDK bootstrap roles (deploy/file-publishing/lookup) for the
    `hnb659fds` qualifier — the standard trust-the-bootstrap-roles pattern. This role itself
    is deliberately *not* given direct create/update/delete permissions on any resource type;
    CDK's own bootstrap roles already have the broad permissions a deploy needs, scoped by
    CDK's own IAM policies, so duplicating that here would just be two copies of the same
    blast radius to keep in sync.
  - cloudformation:Describe*/List* on `ModelForge*-{env}*` stacks and the CDKToolkit stack,
    so `cdk deploy`/`cdk diff` can read stack state and status from the top-level credentials
    (the actual mutating calls happen inside the assumed bootstrap deploy role).
  - ecr:GetAuthorizationToken (account-wide; this action has no resource-level permissions)
    plus the push/pull actions scoped to `modelforge-*` repositories, for the worker image
    build-and-push step.
  - s3 object/list actions scoped to the WebStack site bucket (named deterministically in
    web_stack.py precisely so this role can be scoped to it without a prior deploy), and
    cloudfront:CreateInvalidation, for the frontend sync step.
  - cognito-idp:AdminInitiateAuth, dev only, so the post-deploy smoke test can sign in a
    test user non-interactively (see auth_stack.py's `admin_user_password` flow).

A second role, `PlanRole` (dev only), trusts `pull_request` runs for read-only `cdk diff`
comments — see its own docstring note below for why this isn't just DeployRole with a
wider trust condition.

Cost: an IAM OIDC provider and role cost nothing. See docs/COSTS.md.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

_CDK_QUALIFIER = "hnb659fds"
_GITHUB_OIDC_THUMBPRINTS = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
_GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"


class GithubOidcStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        github_repo: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        account = Stack.of(self).account
        region = Stack.of(self).region
        is_dev = env_name == "dev"

        provider = iam.OpenIdConnectProvider(
            self,
            "GithubOidcProvider",
            url=_GITHUB_OIDC_URL,
            client_ids=["sts.amazonaws.com"],
            thumbprints=_GITHUB_OIDC_THUMBPRINTS,
        )

        # dev deploys from any push to main; prod deploys only through the GitHub
        # Environment named "production", which is where branch-protection-style required
        # reviewers for prod actually live (GitHub Environments, not branch protection).
        sub_condition = (
            f"repo:{github_repo}:ref:refs/heads/main"
            if is_dev
            else f"repo:{github_repo}:environment:production"
        )

        self.deploy_role = role = iam.Role(
            self,
            "DeployRole",
            role_name=f"modelforge-deploy-{env_name}",
            assumed_by=iam.FederatedPrincipal(
                provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                    "StringLike": {"token.actions.githubusercontent.com:sub": sub_condition},
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )

        role.add_to_policy(
            iam.PolicyStatement(
                sid="AssumeCdkBootstrapRoles",
                actions=["sts:AssumeRole"],
                resources=[
                    f"arn:aws:iam::{account}:role/cdk-{_CDK_QUALIFIER}-deploy-role-{account}-{region}",
                    f"arn:aws:iam::{account}:role/cdk-{_CDK_QUALIFIER}-file-publishing-role-{account}-{region}",
                    f"arn:aws:iam::{account}:role/cdk-{_CDK_QUALIFIER}-lookup-role-{account}-{region}",
                ],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudFormationReadForCdkCli",
                actions=[
                    "cloudformation:DescribeStacks",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStackResources",
                    "cloudformation:GetTemplate",
                    "cloudformation:ListStacks",
                    "cloudformation:ListStackResources",
                ],
                resources=[
                    f"arn:aws:cloudformation:{region}:{account}:stack/ModelForge*-{env_name}*/*",
                    f"arn:aws:cloudformation:{region}:{account}:stack/CDKToolkit/*",
                ],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrAuth",
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrPushPullWorkerImages",
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:BatchGetImage",
                    "ecr:CompleteLayerUpload",
                    "ecr:DescribeRepositories",
                    "ecr:InitiateLayerUpload",
                    "ecr:PutImage",
                    "ecr:UploadLayerPart",
                ],
                resources=[f"arn:aws:ecr:{region}:{account}:repository/modelforge-*"],
            )
        )

        site_bucket_arn = f"arn:aws:s3:::modelforge-web-{env_name}-{account}"
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SyncFrontendToSiteBucket",
                actions=["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                resources=[site_bucket_arn, f"{site_bucket_arn}/*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="InvalidateCloudFront",
                actions=["cloudfront:CreateInvalidation"],
                resources=[f"arn:aws:cloudfront::{account}:distribution/*"],
            )
        )

        if is_dev:
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="SmokeTestSignIn",
                    actions=["cognito-idp:AdminInitiateAuth"],
                    resources=[f"arn:aws:cognito-idp:{region}:{account}:userpool/*"],
                )
            )

        # Read-only role for `cdk diff` on pull requests. PRs run on an untrusted (to prod
        # standards) merge ref, never `refs/heads/main`, so DeployRole's trust condition
        # never matches them — this is a second, deliberately narrower role rather than
        # widening DeployRole's trust to cover pull_request too, which would hand every PR
        # (including, in principle, one from a fork) ECR push, S3 write, and Cognito
        # AdminInitiateAuth. Only the CDK lookup role is assumable here; `cdk diff` reads
        # (it never mutates), so there is no need for the deploy or file-publishing roles.
        if is_dev:
            self.plan_role = plan_role = iam.Role(
                self,
                "PlanRole",
                role_name=f"modelforge-plan-{env_name}",
                assumed_by=iam.FederatedPrincipal(
                    provider.open_id_connect_provider_arn,
                    conditions={
                        "StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                        },
                        "StringLike": {
                            "token.actions.githubusercontent.com:sub": (
                                f"repo:{github_repo}:pull_request"
                            )
                        },
                    },
                    assume_role_action="sts:AssumeRoleWithWebIdentity",
                ),
            )
            plan_role.add_to_policy(
                iam.PolicyStatement(
                    sid="AssumeCdkLookupRole",
                    actions=["sts:AssumeRole"],
                    resources=[
                        f"arn:aws:iam::{account}:role/cdk-{_CDK_QUALIFIER}-lookup-role-{account}-{region}",
                    ],
                )
            )
            plan_role.add_to_policy(
                iam.PolicyStatement(
                    sid="CloudFormationReadForCdkDiff",
                    actions=[
                        "cloudformation:DescribeStacks",
                        "cloudformation:GetTemplate",
                        "cloudformation:ListStacks",
                        "cloudformation:ListStackResources",
                    ],
                    resources=[
                        f"arn:aws:cloudformation:{region}:{account}:stack/ModelForge*-{env_name}*/*",
                        f"arn:aws:cloudformation:{region}:{account}:stack/CDKToolkit/*",
                    ],
                )
            )
