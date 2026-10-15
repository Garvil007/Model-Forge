"""CDK app entry point. `cdk deploy ModelForgeAuthStack-dev` deploys only the AuthStack."""

from __future__ import annotations

import os

from aws_cdk import App, Environment

from stacks.auth_stack import AuthStack

app = App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

# The Cognito hosted domain prefix must be globally unique; suffixing with the account id
# keeps it stable across redeploys without colliding with anyone else's dev stack.
domain_prefix = f"modelforge-dev-{account[-6:]}" if account else "modelforge-dev"

AuthStack(
    app,
    "ModelForgeAuthStack-dev",
    env_name="dev",
    hosted_domain_prefix=domain_prefix,
    callback_urls=[
        "http://localhost:5173/",
        "https://app.modelforge.example.com/",
    ],
    logout_urls=[
        "http://localhost:5173/login",
        "https://app.modelforge.example.com/login",
    ],
    env=Environment(account=account, region=region),
)

app.synth()
