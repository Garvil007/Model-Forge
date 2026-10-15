"""AuthStack: Cognito user pool, hosted domain, public app client, optional Google IdP.

Cost: a Cognito user pool is free for the first 10,000 monthly active users, with no Lambda
triggers or advanced security features added here; the hosted domain is free; this stack adds
no ALB, API Gateway custom domain, or ACM certificate. Deploying it alone should cost $0 — see
docs/COSTS.md. Email delivery uses Cognito's own built-in sender, which is free but capped at a
low daily volume; move to SES (see docs/COSTS.md) once real signup volume needs it.
"""

from __future__ import annotations

from typing import Any

import boto3
from aws_cdk import CfnOutput, RemovalPolicy, SecretValue, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ssm as ssm
from constructs import Construct

GOOGLE_CLIENT_ID_PARAM = "/modelforge/{env}/google-client-id"
GOOGLE_CLIENT_SECRET_PARAM = "/modelforge/{env}/google-client-secret"  # SecureString


def _parameter_version(ssm_client: Any, name: str) -> int | None:
    """Current version of an SSM parameter, or None if it doesn't exist yet.

    Only metadata is requested (`describe_parameters`): the parameter's value — including the
    Google client secret — is never read during `cdk synth`. Cognito resolves the actual value
    itself at deploy time, via the dynamic references built below.
    """
    response = ssm_client.describe_parameters(
        ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
    )
    params = response.get("Parameters", [])
    return int(params[0]["Version"]) if params else None


class AuthStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        hosted_domain_prefix: str,
        callback_urls: list[str],
        logout_urls: list[str],
        ssm_client: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        region = Stack.of(self).region

        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"modelforge-{env_name}",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            email=cognito.UserPoolEmail.with_cognito(),
            removal_policy=RemovalPolicy.DESTROY,
        )

        domain = user_pool.add_domain(
            "HostedDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=hosted_domain_prefix),
        )

        supported_idps = [cognito.UserPoolClientIdentityProvider.COGNITO]
        google_idp = self._maybe_add_google_idp(user_pool, env_name, ssm_client, region)
        if google_idp is not None:
            supported_idps.append(cognito.UserPoolClientIdentityProvider.GOOGLE)

        client = user_pool.add_client(
            "WebClient",
            user_pool_client_name=f"modelforge-web-{env_name}",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=callback_urls,
                logout_urls=logout_urls,
            ),
            supported_identity_providers=supported_idps,
            prevent_user_existence_errors=True,
        )
        if google_idp is not None:
            client.node.add_dependency(google_idp)

        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=client.user_pool_client_id)
        CfnOutput(self, "UserPoolRegion", value=region)
        CfnOutput(
            self,
            "HostedDomain",
            value=f"{domain.domain_name}.auth.{region}.amazoncognito.com",
        )
        CfnOutput(self, "GoogleIdpEnabled", value=str(google_idp is not None))

    def _maybe_add_google_idp(
        self,
        user_pool: cognito.UserPool,
        env_name: str,
        ssm_client: Any,
        region: str,
    ) -> cognito.UserPoolIdentityProviderGoogle | None:
        client = ssm_client if ssm_client is not None else boto3.client("ssm", region_name=region)
        client_id_param = GOOGLE_CLIENT_ID_PARAM.format(env=env_name)
        client_secret_param = GOOGLE_CLIENT_SECRET_PARAM.format(env=env_name)

        if _parameter_version(client, client_id_param) is None:
            return None
        secret_version = _parameter_version(client, client_secret_param)
        if secret_version is None:
            return None

        return cognito.UserPoolIdentityProviderGoogle(
            self,
            "GoogleIdp",
            user_pool=user_pool,
            client_id=ssm.StringParameter.value_for_string_parameter(self, client_id_param),
            client_secret_value=SecretValue.ssm_secure(client_secret_param),
            scopes=["email", "profile", "openid"],
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.GOOGLE_EMAIL,
            ),
        )
