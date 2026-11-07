"""GPU kill switch: an SSM String parameter that stops new GPU jobs being queued.

Checked both at `POST /jobs` (so the user gets an immediate, clear error instead of a
job stuck at "queued") and again at dispatch time (so a job queued just before the
switch flipped still doesn't reach Batch). Fails *open* on an SSM read error — a
transient SSM outage shouldn't itself take GPU jobs down.
"""

from __future__ import annotations

import os
from typing import Any

_PARAMETER_VALUE_ON = "on"


def _env_name() -> str:
    return os.environ.get("MF_ENV_NAME", "dev")


def kill_switch_parameter_name() -> str:
    return f"/modelforge/{_env_name()}/gpu-kill-switch"


def _ssm_client() -> Any:
    import boto3

    return boto3.client(
        "ssm",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def gpu_kill_switch_enabled(client: Any = None) -> bool:
    ssm = client if client is not None else _ssm_client()
    try:
        response = ssm.get_parameter(Name=kill_switch_parameter_name())
    except Exception:  # noqa: BLE001 — ParameterNotFound or a transient SSM error: fail open
        return False
    return response["Parameter"]["Value"].strip().lower() == _PARAMETER_VALUE_ON
