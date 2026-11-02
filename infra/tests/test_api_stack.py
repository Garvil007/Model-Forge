"""ApiStack synth tests — offline, no deploy, no real Docker build.

Docker-image Lambda assets need a real `docker build` at synth time (CDK shells out to
the Docker CLI), so these tests monkeypatch `DockerImageCode.from_image_asset` with a
fake asset code rather than requiring Docker in CI.
"""

from __future__ import annotations

from unittest.mock import patch

from aws_cdk import App, Environment
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_lambda as lambda_
from aws_cdk.assertions import Match, Template

from stacks.api_stack import ApiStack
from stacks.data_stack import DataStack

_ENV = Environment(account="123456789012", region="us-east-1")


def _synth_template() -> Template:
    app = App()
    data = DataStack(app, "TestDataStackForApi", env_name="dev", env=_ENV)
    fake_repo = ecr.Repository.from_repository_name(data, "FakeRepo", "fake-repo")
    fake_code = lambda_.DockerImageCode.from_ecr(fake_repo, tag_or_digest="latest")

    with patch.object(lambda_.DockerImageCode, "from_image_asset", return_value=fake_code):
        stack = ApiStack(
            app,
            "TestApiStack",
            env_name="dev",
            table=data.table,
            uploads_bucket=data.uploads_bucket,
            results_bucket=data.results_bucket,
            system_jobs_queue=data.system_jobs,
            cpu_jobs_queue=data.cpu_jobs,
            gpu_jobs_queue=data.gpu_jobs,
            hf_token_key=data.hf_token_key,
            cognito_user_pool_id="us-east-1_fake",
            cognito_region="us-east-1",
            cognito_client_id="fakeclientid",
            api_code_path=".",
            env=_ENV,
        )
    return Template.from_stack(stack)


def test_log_retention_is_one_week():
    template = _synth_template()
    template.has_resource_properties(
        "Custom::LogRetention", Match.object_like({"RetentionInDays": 7})
    )


def test_no_reserved_concurrency_configured():
    # This account's Lambda concurrency limit is only 10 (new-account default); AWS
    # requires >=10 unreserved account-wide, so reserving any amount fails deploy. See
    # api_stack.py's module docstring.
    template = _synth_template()
    functions = template.find_resources("AWS::Lambda::Function")
    for fn in functions.values():
        assert "ReservedConcurrentExecutions" not in fn["Properties"]


def test_http_api_exists():
    template = _synth_template()
    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)
