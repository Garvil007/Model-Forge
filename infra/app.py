"""CDK app entry point. `cdk deploy ModelForge<X>Stack-dev` deploys only that stack;
`cdk deploy --all -c env=dev` deploys everything.

Stack order: NetworkStack -> DataStack -> AuthStack -> BatchStack -> ApiStack -> WebStack
-> AlarmsStack. AuthStack's Cognito callback/logout URLs can't include the real
CloudFront domain on a first deploy — WebStack's distribution domain isn't known until
WebStack itself has deployed, and CloudFront's default certificate means there's no
custom domain to predict ahead of time. See docs/decisions.md ("Day 19: Cognito callback
URL vs. CloudFront's not-yet-known domain") for the two-deploy reality: deploy once with
the placeholder below, read WebStack's `DistributionDomainName` output, then redeploy
*only* AuthStack with that domain added to `callback_urls`/`logout_urls`.
"""

from __future__ import annotations

import os

from aws_cdk import App, Environment

from stacks.alarms_stack import AlarmsStack
from stacks.api_stack import ApiStack
from stacks.auth_stack import AuthStack
from stacks.batch_stack import BatchStack
from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.web_stack import WebStack

app = App()
env_name = app.node.try_get_context("env") or "dev"

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
cdk_env = Environment(account=account, region=region)

# The Cognito hosted domain prefix must be globally unique; suffixing with the account id
# keeps it stable across redeploys without colliding with anyone else's dev stack.
domain_prefix = f"modelforge-{env_name}-{account[-6:]}" if account else f"modelforge-{env_name}"

budget_email = os.environ.get("MF_BUDGET_NOTIFICATION_EMAIL", "garvilazure0112@gmail.com")

network_stack = NetworkStack(app, f"ModelForgeNetworkStack-{env_name}", env=cdk_env)

data_stack = DataStack(
    app, f"ModelForgeDataStack-{env_name}", env_name=env_name, env=cdk_env
)

# Placeholder callback/logout URLs on a first deploy — see module docstring. Once
# WebStack's CloudFront domain is known, add `f"https://{distribution_domain}/"` (and
# `/login` for logout) here and redeploy AuthStack alone.
auth_stack = AuthStack(
    app,
    f"ModelForgeAuthStack-{env_name}",
    env_name=env_name,
    hosted_domain_prefix=domain_prefix,
    callback_urls=[
        "http://localhost:5173/",
        "https://d2ozjxxhkp5644.cloudfront.net/",
    ],
    logout_urls=[
        "http://localhost:5173/login",
        "https://d2ozjxxhkp5644.cloudfront.net/login",
    ],
    env=cdk_env,
)

batch_stack = BatchStack(
    app,
    f"ModelForgeBatchStack-{env_name}",
    env_name=env_name,
    vpc=network_stack.vpc,
    worker_security_group=network_stack.worker_security_group,
    uploads_bucket_arn=data_stack.uploads_bucket.bucket_arn,
    uploads_bucket_name=data_stack.uploads_bucket.bucket_name,
    results_bucket_arn=data_stack.results_bucket.bucket_arn,
    results_bucket_name=data_stack.results_bucket.bucket_name,
    table_arn=data_stack.table.table_arn,
    cpu_jobs_queue=data_stack.cpu_jobs,
    gpu_jobs_queue=data_stack.gpu_jobs,
    dispatcher_code_path="..",
    env=cdk_env,
)

api_stack = ApiStack(
    app,
    f"ModelForgeApiStack-{env_name}",
    env_name=env_name,
    table=data_stack.table,
    uploads_bucket=data_stack.uploads_bucket,
    results_bucket=data_stack.results_bucket,
    system_jobs_queue=data_stack.system_jobs,
    cpu_jobs_queue=data_stack.cpu_jobs,
    gpu_jobs_queue=data_stack.gpu_jobs,
    hf_token_key=data_stack.hf_token_key,
    cognito_user_pool_id=auth_stack.user_pool.user_pool_id,
    cognito_region=region,
    cognito_client_id=auth_stack.web_client.user_pool_client_id,
    api_code_path="..",
    gpu_kill_switch=batch_stack.gpu_kill_switch,
    web_base_url=os.environ.get("MF_WEB_BASE_URL", "http://localhost:5173"),
    env=cdk_env,
)

web_stack = WebStack(
    app,
    f"ModelForgeWebStack-{env_name}",
    env_name=env_name,
    http_api=api_stack.http_api,
    env=cdk_env,
)

alarms_stack = AlarmsStack(
    app,
    f"ModelForgeAlarmsStack-{env_name}",
    env_name=env_name,
    cpu_jobs_dlq=data_stack.cpu_jobs_dlq,
    gpu_jobs_dlq=data_stack.gpu_jobs_dlq,
    system_jobs_dlq=data_stack.system_jobs_dlq,
    dispatcher_function=batch_stack.dispatcher,
    api_function=api_stack.function,
    budget_notification_email=budget_email,
    cost_report_code_path="..",
    env=cdk_env,
)

app.synth()
