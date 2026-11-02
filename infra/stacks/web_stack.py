"""WebStack: S3 + CloudFront (Origin Access Control) for the built `apps/web` SPA,
`/api/*` routed to the ApiStack HTTP API on the same domain, security headers, long cache
on hashed Vite assets, no-cache on `index.html` (so a deploy is visible immediately
without a cache-busted filename), SPA client-side routing (403/404 -> `/index.html`).

No custom domain / ACM certificate yet — CloudFront's own default certificate
(`*.cloudfront.net`) is used, matching AuthStack's "no custom domain" note. Add a
Route 53 hosted zone + ACM cert + `domain_names`/`certificate` on the distribution once a
real domain exists (see docs/decisions.md).

Cost: CloudFront has no fixed monthly fee (pay per request + per-GB data transfer, with
a perpetual free tier); the S3 bucket holds a few MB of static assets. Nothing always-on.
See docs/COSTS.md.
"""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from constructs import Construct


class WebStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        http_api: apigwv2.IHttpApi,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        is_dev = env_name == "dev"

        self.site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY if is_dev else RemovalPolicy.RETAIN,
            auto_delete_objects=is_dev,
        )

        security_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "SecurityHeadersPolicy",
            response_headers_policy_name=f"modelforge-security-headers-{env_name}",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365),
                    include_subdomains=True,
                    override=True,
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(
                    override=True
                ),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY, override=True
                ),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True,
                ),
            ),
        )

        no_cache_policy = cloudfront.CachePolicy(
            self,
            "NoCachePolicy",
            cache_policy_name=f"modelforge-spa-shell-no-cache-{env_name}",
            default_ttl=Duration.seconds(0),
            min_ttl=Duration.seconds(0),
            max_ttl=Duration.seconds(0),
        )

        asset_origin = origins.S3BucketOrigin.with_origin_access_control(self.site_bucket)
        api_origin = origins.HttpOrigin(
            f"{http_api.api_id}.execute-api.{self.region}.amazonaws.com",
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
        )

        # apps/api's FastAPI routes have no "/api" prefix (e.g. "/catalog", not
        # "/api/catalog") — CloudFront forwards the viewer's path to the origin
        # unchanged, so without this the origin sees "/api/catalog" and 404s. Strips the
        # "/api" prefix at the edge before the request reaches API Gateway.
        strip_api_prefix = cloudfront.Function(
            self,
            "StripApiPrefixFunction",
            function_name=f"modelforge-strip-api-prefix-{env_name}",
            code=cloudfront.FunctionCode.from_inline(
                "function handler(event) {\n"
                "  var request = event.request;\n"
                "  request.uri = request.uri.replace(/^\\/api/, '') || '/';\n"
                "  return request;\n"
                "}\n"
            ),
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=asset_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=no_cache_policy,
                response_headers_policy=security_headers,
            ),
            additional_behaviors={
                "/assets/*": cloudfront.BehaviorOptions(
                    origin=asset_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                    response_headers_policy=security_headers,
                ),
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                    function_associations=[
                        cloudfront.FunctionAssociation(
                            function=strip_api_prefix,
                            event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                        )
                    ],
                ),
            },
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        CfnOutput(self, "DistributionDomainName", value=self.distribution.distribution_domain_name)
        CfnOutput(self, "SiteBucketName", value=self.site_bucket.bucket_name)
        CfnOutput(self, "DistributionId", value=self.distribution.distribution_id)
