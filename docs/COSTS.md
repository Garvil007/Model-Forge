# Costs

Every AWS resource, whether it costs anything at idle, and the per-job cost. Updated as infra is deployed.

## Day 8 — Cognito (`infra/stacks/auth_stack.py`)

| Resource | Idle cost | Notes |
|---|---|---|
| Cognito user pool | $0 | Free for the first 10,000 monthly active users (no advanced security features, no Lambda triggers added here). |
| Hosted domain (`*.auth.<region>.amazoncognito.com`) | $0 | No custom domain / ACM certificate — avoids the certificate and Route 53 costs a custom domain would add. |
| Cognito built-in email sending | $0 | Low daily send limit (a per-account cap, not configurable). **Upgrade to SES** once real signup volume needs it — SES is ~$0.10 per 1,000 emails and removes the daily cap, but needs a verified sending domain first. |
| Google identity provider | $0 | Only added if `/modelforge/<env>/google-client-id` and `-client-secret` exist in SSM Parameter Store; skipped entirely otherwise. SSM Standard parameters are free. |
| SSM Parameter Store (Standard tier) | $0 | Free tier covers this; no Advanced parameters used. |

No ALB, API Gateway custom domain, NAT gateway, or other always-on compute is added by this
stack — deploying `ModelForgeAuthStack-dev` alone should show $0 on the next bill, confirmed
by `cdk synth` (no unexpected resources in the synthesized template) prior to deploy.
