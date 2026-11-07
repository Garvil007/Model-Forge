"""Stripe secret key and webhook signing secret — both read from SSM Parameter Store
(SecureString) at call time, mirroring `modelforge_db.kill_switch`'s pattern. Never cached
across requests inside one Lambda execution environment the way a module-level global
would be: unlike the kill switch, a stale secret here is not a safe failure mode, so each
call re-reads SSM (which API Gateway's Lambda already keeps warm, and SSM itself caches
parameter reads at the AWS edge)."""

from __future__ import annotations

import os
from typing import Any


def _env_name() -> str:
    return os.environ.get("MF_ENV_NAME", "dev")


def _ssm_client() -> Any:
    import boto3

    return boto3.client(
        "ssm",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def _get_secret(name: str, *, override_env_var: str, client: Any = None) -> str:
    # Local dev / tests set the override env var instead of standing up real SSM.
    override = os.environ.get(override_env_var)
    if override:
        return override
    ssm = client if client is not None else _ssm_client()
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]


def get_stripe_secret_key(client: Any = None) -> str:
    return _get_secret(
        f"/modelforge/{_env_name()}/stripe-secret-key",
        override_env_var="MF_STRIPE_SECRET_KEY_OVERRIDE",
        client=client,
    )


def get_stripe_webhook_secret(client: Any = None) -> str:
    return _get_secret(
        f"/modelforge/{_env_name()}/stripe-webhook-secret",
        override_env_var="MF_STRIPE_WEBHOOK_SECRET_OVERRIDE",
        client=client,
    )
