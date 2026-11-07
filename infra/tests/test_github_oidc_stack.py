"""GithubOidcStack synth tests — offline, no deploy."""

from __future__ import annotations

from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from stacks.github_oidc_stack import GithubOidcStack

_ENV = Environment(account="123456789012", region="us-east-1")
_REPO = "Garvil007/Model-Forge"


def _synth_template(env_name: str) -> Template:
    app = App()
    stack = GithubOidcStack(
        app, f"TestGithubOidcStack-{env_name}", env_name=env_name, github_repo=_REPO, env=_ENV
    )
    return Template.from_stack(stack)


def test_creates_exactly_one_oidc_provider():
    template = _synth_template("dev")
    template.resource_count_is("Custom::AWSCDKOpenIdConnectProvider", 1)


def test_dev_role_trusts_only_main_branch_pushes():
    template = _synth_template("dev")
    template.has_resource_properties(
        "AWS::IAM::Role",
        Match.object_like(
            {
                "RoleName": "modelforge-deploy-dev",
                "AssumeRolePolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Condition": Match.object_like(
                                            {
                                                "StringLike": {
                                                    "token.actions.githubusercontent.com:sub": (
                                                        f"repo:{_REPO}:ref:refs/heads/main"
                                                    )
                                                }
                                            }
                                        )
                                    }
                                )
                            ]
                        )
                    }
                ),
            }
        ),
    )


def test_prod_role_trusts_only_the_production_environment():
    template = _synth_template("prod")
    template.has_resource_properties(
        "AWS::IAM::Role",
        Match.object_like(
            {
                "RoleName": "modelforge-deploy-prod",
                "AssumeRolePolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Condition": Match.object_like(
                                            {
                                                "StringLike": {
                                                    "token.actions.githubusercontent.com:sub": (
                                                        f"repo:{_REPO}:environment:production"
                                                    )
                                                }
                                            }
                                        )
                                    }
                                )
                            ]
                        )
                    }
                ),
            }
        ),
    )


def test_prod_role_has_no_cognito_smoke_test_permission():
    template = _synth_template("prod")
    policies = template.find_resources("AWS::IAM::Policy")
    all_actions = [
        action
        for policy in policies.values()
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
        for action in (
            statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
        )
    ]
    assert "cognito-idp:AdminInitiateAuth" not in all_actions


def test_no_policy_statement_grants_wildcard_resource_on_mutating_actions():
    template = _synth_template("dev")
    policies = template.find_resources("AWS::IAM::Policy")
    for policy in policies.values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            if statement.get("Sid") == "EcrAuth":
                continue  # GetAuthorizationToken has no resource-level permissions by design
            resources = (
                statement["Resource"]
                if isinstance(statement["Resource"], list)
                else [statement["Resource"]]
            )
            assert "*" not in resources, statement
