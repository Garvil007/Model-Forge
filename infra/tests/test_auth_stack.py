"""AuthStack synth tests — a fake SSM client keeps these fully offline."""

from __future__ import annotations

from typing import Any

from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stacks.auth_stack import AuthStack


class _FakeSsmClient:
    """Reports no parameters found — the default, Google-IdP-absent case."""

    def __init__(self, known_names: set[str] | None = None) -> None:
        self._known_names = known_names or set()

    def describe_parameters(self, **kwargs: Any) -> dict[str, Any]:
        requested = kwargs["ParameterFilters"][0]["Values"][0]
        if requested in self._known_names:
            return {"Parameters": [{"Version": 1}]}
        return {"Parameters": []}


def _synth_template(ssm_client: Any = None) -> Template:
    app = App()
    stack = AuthStack(
        app,
        "TestAuthStack",
        env_name="test",
        hosted_domain_prefix="modelforge-test-123456",
        callback_urls=["http://localhost:5173/"],
        logout_urls=["http://localhost:5173/login"],
        ssm_client=ssm_client or _FakeSsmClient(),
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


def test_creates_one_user_pool_with_self_signup() -> None:
    template = _synth_template()
    template.resource_count_is("AWS::Cognito::UserPool", 1)
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {"AdminCreateUserConfig": {"AllowAdminCreateUserOnly": False}},
    )


def test_creates_hosted_domain() -> None:
    template = _synth_template()
    template.resource_count_is("AWS::Cognito::UserPoolDomain", 1)


def test_public_client_has_no_secret_and_uses_auth_code_grant() -> None:
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {"GenerateSecret": False, "AllowedOAuthFlows": ["code"]},
    )


def test_google_idp_skipped_when_ssm_parameters_absent() -> None:
    template = _synth_template()
    template.resource_count_is("AWS::Cognito::UserPoolIdentityProvider", 0)


def test_google_idp_added_when_ssm_parameters_present() -> None:
    known = {
        "/modelforge/test/google-client-id",
        "/modelforge/test/google-client-secret",
    }
    template = _synth_template(_FakeSsmClient(known))
    template.resource_count_is("AWS::Cognito::UserPoolIdentityProvider", 1)


def test_outputs_user_pool_id_client_id_and_domain() -> None:
    template = _synth_template()
    outputs = template.to_json()["Outputs"]
    assert "UserPoolId" in outputs
    assert "UserPoolClientId" in outputs
    assert "HostedDomain" in outputs
