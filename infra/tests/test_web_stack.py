"""WebStack synth tests — offline, no deploy."""

from __future__ import annotations

from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from stacks.web_stack import WebStack

_ENV = Environment(account="123456789012", region="us-east-1")


def _fake_http_api(app):
    from aws_cdk import Stack
    from aws_cdk import aws_apigatewayv2 as apigwv2

    helper = Stack(app, "HelperStackForWeb", env=_ENV)
    return apigwv2.HttpApi(helper, "FakeHttpApi")


def _synth_template() -> Template:
    app = App()
    http_api = _fake_http_api(app)
    stack = WebStack(app, "TestWebStack", env_name="dev", http_api=http_api, env=_ENV)
    return Template.from_stack(stack)


def test_origin_access_control_exists():
    template = _synth_template()
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)


def test_bucket_blocks_public_access():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        Match.object_like(
            {
                "PublicAccessBlockConfiguration": Match.object_like(
                    {"BlockPublicAcls": True, "BlockPublicPolicy": True}
                )
            }
        ),
    )


def test_api_behavior_present():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        Match.object_like(
            {
                "DistributionConfig": Match.object_like(
                    {
                        "CacheBehaviors": Match.array_with(
                            [Match.object_like({"PathPattern": "/api/*"})]
                        )
                    }
                )
            }
        ),
    )


def test_api_behavior_strips_prefix_at_the_edge():
    template = _synth_template()
    template.resource_count_is("AWS::CloudFront::Function", 1)
    template.has_resource_properties(
        "AWS::CloudFront::Function",
        Match.object_like({"FunctionCode": Match.string_like_regexp(r"replace\(/\^\\/api/")}),
    )
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        Match.object_like(
            {
                "DistributionConfig": Match.object_like(
                    {
                        "CacheBehaviors": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "PathPattern": "/api/*",
                                        "FunctionAssociations": Match.array_with(
                                            [Match.object_like({"EventType": "viewer-request"})]
                                        ),
                                    }
                                )
                            ]
                        )
                    }
                )
            }
        ),
    )


def test_content_security_policy_has_no_unsafe_inline_script_or_style():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::CloudFront::ResponseHeadersPolicy",
        Match.object_like(
            {
                "ResponseHeadersPolicyConfig": Match.object_like(
                    {
                        "SecurityHeadersConfig": Match.object_like(
                            {
                                "ContentSecurityPolicy": Match.object_like(
                                    {
                                        "ContentSecurityPolicy": Match.string_like_regexp(
                                            r"script-src 'self';"
                                        ),
                                        "Override": True,
                                    }
                                )
                            }
                        )
                    }
                )
            }
        ),
    )
    template.has_resource_properties(
        "AWS::CloudFront::ResponseHeadersPolicy",
        Match.object_like(
            {
                "ResponseHeadersPolicyConfig": Match.object_like(
                    {
                        "SecurityHeadersConfig": Match.object_like(
                            {
                                "ContentSecurityPolicy": Match.object_like(
                                    {
                                        "ContentSecurityPolicy": Match.string_like_regexp(
                                            r"style-src 'self';"
                                        ),
                                    }
                                )
                            }
                        )
                    }
                )
            }
        ),
    )


def test_cloudfront_distribution_has_a_per_ip_rate_limit_web_acl():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::WAFv2::WebACL",
        Match.object_like(
            {
                "Scope": "CLOUDFRONT",
                "Rules": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Statement": Match.object_like(
                                    {
                                        "RateBasedStatement": Match.object_like(
                                            {"AggregateKeyType": "IP"}
                                        )
                                    }
                                )
                            }
                        )
                    ]
                ),
            }
        ),
    )
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        Match.object_like(
            {"DistributionConfig": Match.object_like({"WebACLId": Match.any_value()})}
        ),
    )


def test_spa_fallback_error_responses_present():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        Match.object_like(
            {
                "DistributionConfig": Match.object_like(
                    {
                        "CustomErrorResponses": Match.array_with(
                            [
                                Match.object_like(
                                    {"ErrorCode": 404, "ResponseCode": 200}
                                )
                            ]
                        )
                    }
                )
            }
        ),
    )
