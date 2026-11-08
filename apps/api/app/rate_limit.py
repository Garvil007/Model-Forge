"""Per-user and per-IP rate limiting for sensitive write endpoints (job creation,
uploads, Hugging Face import, Stripe checkout/portal session creation).

Lambda invocations don't share process memory, so an in-process token bucket wouldn't
see traffic from other warm instances. `RateLimitRepository` instead counts requests in
the same DynamoDB table everything else here lives in, via an atomic conditional ADD —
safe under concurrent requests, no read-modify-write race (see
packages/db/src/modelforge_db/repositories/rate_limits.py).

Each limited endpoint gets two independent checks: one keyed by user id and one keyed by
client IP. The IP check exists because a single user can only ever be caught by the user
check *after* authenticating; without it, one attacker could spin up many accounts (or
hit unauthenticated/public routes) and still flood the API from one network location.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from modelforge_db.records import UserRecord
from modelforge_db.repositories.rate_limits import RateLimitRepository

from .auth import current_user
from .errors import ApiError

_RATE_LIMITED_MESSAGE = "Too many requests. Please slow down and try again shortly."


def get_rate_limit_repository() -> RateLimitRepository:
    return RateLimitRepository()


def client_ip(request: Request) -> str:
    """Best-effort real client IP. CloudFront sits in front of API Gateway here (see
    infra/stacks/web_stack.py) and appends the viewer's address as the *last* entry of
    `X-Forwarded-For` (any earlier entries are whatever the client itself sent and are
    attacker-controlled — trusting the leftmost entry lets a client spoof its own IP and
    bypass this limiter entirely). `request.client.host` would otherwise be CloudFront's
    own edge IP, not the caller's, so it's only a fallback for local dev / direct calls.

    This still assumes CloudFront is the only path to API Gateway — if the API Gateway
    default `execute-api` endpoint is ever reachable directly, a caller can inject this
    header unobstructed."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(
    scope: str,
    *,
    user_limit: int,
    user_window_seconds: int,
    ip_limit: int,
    ip_window_seconds: int,
) -> object:
    """FastAPI dependency factory enforcing both limits for one endpoint. `scope` is a
    short, endpoint-specific string (e.g. "jobs.create") so different endpoints don't
    share a bucket."""

    def _check_rate_limit(
        request: Request,
        user: Annotated[UserRecord, Depends(current_user)],
        limiter: Annotated[RateLimitRepository, Depends(get_rate_limit_repository)],
    ) -> None:
        if not limiter.increment_and_check(
            f"ip:{scope}", client_ip(request), limit=ip_limit, window_seconds=ip_window_seconds
        ):
            raise ApiError(429, "rate_limited", _RATE_LIMITED_MESSAGE)
        if not limiter.increment_and_check(
            f"user:{scope}", user.user_id, limit=user_limit, window_seconds=user_window_seconds
        ):
            raise ApiError(429, "rate_limited", _RATE_LIMITED_MESSAGE)

    return Depends(_check_rate_limit)
