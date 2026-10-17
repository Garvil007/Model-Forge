"""CDK app entry point. `cdk deploy ModelForgeAuthStack-dev` deploys only the AuthStack."""

from __future__ import annotations

import os

from aws_cdk import App, Environment

from stacks.auth_stack import AuthStack
from stacks.compute_stack import ComputeStack
from stacks.queue_stack import QueueStack
from stacks.storage_stack import StorageStack

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

storage_stack = StorageStack(
    app,
    "ModelForgeStorageStack-dev",
    env_name="dev",
    env=Environment(account=account, region=region),
)

queue_stack = QueueStack(
    app, "ModelForgeQueueStack-dev", env=Environment(account=account, region=region)
)

ComputeStack(
    app,
    "ModelForgeComputeStack-dev",
    uploads_bucket_arn=storage_stack.uploads_bucket.bucket_arn,
    results_bucket_arn=storage_stack.results_bucket.bucket_arn,
    cpu_jobs_queue=queue_stack.cpu_jobs,
    gpu_jobs_queue=queue_stack.gpu_jobs,
    dispatcher_code_path="lambda/dispatcher",
    env=Environment(account=account, region=region),
)

app.synth()
