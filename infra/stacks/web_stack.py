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
from aws_cdk import aws_wafv2 as wafv2
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
        account = Stack.of(self).account

        self.site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            # Named deterministically (rather than CDK-generated) so the GitHub Actions
            # deploy role (see GithubOidcStack) can be scoped to this exact bucket ARN
            # without waiting for a first deploy to learn the generated name.
            bucket_name=f"modelforge-web-{env_name}-{account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY if is_dev else RemovalPolicy.RETAIN,
            auto_delete_objects=is_dev,
        )

        # script-src/style-src have no 'unsafe-inline': index.html has no inline <script> (just
        # the module entrypoint), and the SPA's CSS comes entirely from CSS Modules <link>
        # stylesheets, never injected <style> blocks. `style-src-attr` is relaxed on its own
        # (CSP3 lets browsers split the style-src-attr/style-src-elem checks) because several
        # components set the `style` attribute directly for runtime-computed values (progress bar
        # widths, skeleton sizes) — those values are always numbers interpolated by our own code,
        # never raw user input, so this doesn't reopen a script-injection path; see
        # docs/SECURITY.md for the residual-risk note. connect-src covers same-origin API calls
        # plus the three other origins the SPA actually talks to: Cognito's hosted-UI/token
        # domain, the Cognito IDP API Amplify calls directly, and presigned S3 URLs for
        # multipart model uploads (see useFileUpload.ts / client.ts putPresigned).
        content_security_policy = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "style-src-attr 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self' https://*.amazoncognito.com https://cognito-idp.*.amazonaws.com "
            "https://*.s3.amazonaws.com https://*.s3.*.amazonaws.com; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "upgrade-insecure-requests"
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
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy=content_security_policy,
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

        # Per-IP rate limiting at the edge: CloudFront fronts both the static site and
        # "/api/*" (see api_stack.py's module docstring on why its own throttling can
        # only be an account-wide backstop, not per-IP). A WAFv2 Web ACL for CloudFront
        # must be created in us-east-1 regardless of where this stack otherwise deploys
        # — see infra/app.py, which defaults CDK_DEFAULT_REGION to us-east-1.
        rate_limit_waf = wafv2.CfnWebACL(
            self,
            "RateLimitWebAcl",
            name=f"modelforge-rate-limit-{env_name}",
            scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"modelforge-rate-limit-{env_name}",
                sampled_requests_enabled=True,
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="PerIpRateLimit",
                    priority=0,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            # Requests from one IP in a rolling 5-minute window, across
                            # the whole site (assets + "/api/*"); app.rate_limit's
                            # per-endpoint limits are much tighter for the write
                            # endpoints that actually cost money to abuse.
                            limit=2000,
                            evaluation_window_sec=300,
                            aggregate_key_type="IP",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"modelforge-rate-limit-per-ip-{env_name}",
                        sampled_requests_enabled=True,
                    ),
                )
            ],
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            web_acl_id=rate_limit_waf.attr_arn,
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
