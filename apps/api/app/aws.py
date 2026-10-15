"""Cached boto3 client factories for S3 and SQS, LocalStack-aware."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from .config import Settings, get_settings


@lru_cache(maxsize=1)
def _s3_client_for(region: str, endpoint_url: str) -> Any:
    # request_checksum_calculation/response_checksum_validation="when_required": boto3 >=
    # 1.36 defaults to always sending checksum params on upload_part, which breaks a plain
    # browser PUT against a presigned URL that didn't sign those headers.
    config = Config(
        signature_version="s3v4",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        s3={"addressing_style": "path"} if endpoint_url else {},
    )
    return boto3.client(
        "s3", region_name=region, endpoint_url=endpoint_url or None, config=config
    )


@lru_cache(maxsize=1)
def _sqs_client_for(region: str, endpoint_url: str) -> Any:
    return boto3.client("sqs", region_name=region, endpoint_url=endpoint_url or None)


def get_s3_client(settings: Settings = None) -> Any:  # type: ignore[assignment]
    settings = settings or get_settings()
    return _s3_client_for(settings.aws_region, settings.aws_endpoint_url)


def get_sqs_client(settings: Settings = None) -> Any:  # type: ignore[assignment]
    settings = settings or get_settings()
    return _sqs_client_for(settings.aws_region, settings.aws_endpoint_url)
