"""Cognito access-token verification and the `current_user` dependency.

Access tokens (not ID tokens) are what the frontend attaches to API requests — see
`apps/web/src/auth/cognitoAuthProvider.ts`. An access token carries `sub`, `client_id` and
`token_use`, not a reliable `email` claim, so a brand-new user is provisioned with whatever
email the token happens to carry (often none) and nothing else assumed about them.
"""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient, decode
from jwt.exceptions import InvalidTokenError
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import UserRecord
from modelforge_db.repositories.users import UserRepository

from .config import Settings, get_settings

_JWKS_CACHE_SECONDS = 3600

# One PyJWKClient per issuer URL, reused across requests — each client keeps its own
# time-based cache of the pool's signing keys, so a steady stream of requests doesn't
# refetch JWKS from Cognito.
_jwks_clients: dict[str, PyJWKClient] = {}


def _issuer(settings: Settings) -> str:
    return f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"


def _jwks_client(settings: Settings) -> PyJWKClient:
    jwks_url = f"{_issuer(settings)}/.well-known/jwks.json"
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, lifespan=_JWKS_CACHE_SECONDS)
        _jwks_clients[jwks_url] = client
    return client


def verify_access_token(token: str, settings: Settings) -> dict[str, object]:
    """Verify signature, issuer and expiry; then check it's an access token for this client."""
    try:
        signing_key = _jwks_client(settings).get_signing_key_from_jwt(token).key
        claims = decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=_issuer(settings),
            options={"verify_aud": False},
        )
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from error

    if claims.get("token_use") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")
    if claims.get("client_id") != settings.cognito_client_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token was not issued for this client")
    return claims


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return header.removeprefix("Bearer ")


def get_user_repository() -> UserRepository:
    return UserRepository()


def assert_local_auth_allowed(settings: Settings) -> None:
    """`auth_mode="local"` is a hard bypass of Cognito and must never run outside a
    developer's own machine. Fail hard (not just warn) if it's set anywhere that looks
    like a real deployment — a Lambda runtime always sets AWS_LAMBDA_FUNCTION_NAME."""
    if settings.auth_mode != "local":
        return
    if settings.environment != "local" or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        raise RuntimeError(
            'MF_AUTH_MODE="local" is only allowed when MF_ENVIRONMENT="local" and not '
            "running in Lambda. Refusing to start with an auth bypass enabled here."
        )


def _local_dev_user(settings: Settings, users: UserRepository) -> UserRecord:
    try:
        return users.get_by_id(settings.local_dev_user_id)
    except NotFoundError:
        return users.create(
            settings.local_dev_user_id,
            settings.local_dev_user_email,
            plan=settings.local_dev_plan,
        )


async def current_user(
    request: Request,
    settings: Settings = Depends(get_settings),  # noqa: B008
    users: UserRepository = Depends(get_user_repository),  # noqa: B008
) -> UserRecord:
    assert_local_auth_allowed(settings)
    if settings.auth_mode == "local":
        return _local_dev_user(settings, users)

    claims = verify_access_token(_bearer_token(request), settings)
    user_id = str(claims["sub"])
    try:
        return users.get_by_id(user_id)
    except NotFoundError:
        email = str(claims.get("email", ""))
        return users.create(user_id, email)
