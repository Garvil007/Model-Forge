"""Handles a `detect_format` SystemJobMessage: read the model's header bytes, detect its
real format/family/bits/params/inputs, and write the result back onto the ModelRecord."""

from __future__ import annotations

import os
from typing import Any

import boto3
from modelforge_catalog.uploads import MODEL_EXTENSION_FORMAT, extension_of
from modelforge_db.exceptions import NotFoundError
from modelforge_db.repositories.models import ModelRepository

from core.s3_reader import S3RangeReader

from .detect import DetectionError, sniff_and_detect

_HEADER_PROBE_BYTES = 8 * 1024 * 1024  # enough for GGUF/safetensors headers
_MAX_FULL_FILE_BYTES = 512 * 1024 * 1024
_MAX_RETRIES_BEFORE_PERMANENT_FAIL = 3


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def _format_hint_for(filename: str) -> str | None:
    return MODEL_EXTENSION_FORMAT.get(extension_of(filename))


def handle_detect_format(
    *, user_id: str, model_id: str, approximate_receive_count: int = 1
) -> None:
    models = ModelRepository()
    try:
        record = models.get(user_id, model_id)
    except NotFoundError:
        return  # nothing to detect — already deleted or never existed

    if record.status != "checking":
        return  # idempotent: already handled (retry/duplicate delivery)

    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    if not record.s3_key.startswith(f"users/{user_id}/"):
        models.mark_failed(user_id, model_id, code="forbidden", message="key ownership mismatch")
        return

    s3 = _s3_client()
    reader = S3RangeReader(s3, uploads_bucket, record.s3_key, record.size_bytes)
    extension_hint = _format_hint_for(record.filename)

    try:
        if record.size_bytes <= _MAX_FULL_FILE_BYTES:
            probe = reader.read_all(_MAX_FULL_FILE_BYTES)
        else:
            probe = reader.read(_HEADER_PROBE_BYTES)
        result = sniff_and_detect(probe, record.size_bytes, extension_hint)
    except DetectionError as error:
        if approximate_receive_count >= _MAX_RETRIES_BEFORE_PERMANENT_FAIL:
            models.mark_failed(user_id, model_id, code=error.code, message=str(error))
        return
    except Exception as error:  # noqa: BLE001 — any unexpected parse failure is terminal
        models.mark_failed(user_id, model_id, code="detection_failed", message=str(error))
        return

    details_patch = dict(record.details)
    details_patch.pop("provisional", None)
    details_patch["inputs"] = result.inputs
    details_patch["detectionWarnings"] = result.warnings
    details_patch.update(result.extras)

    models.apply_detection(
        user_id,
        model_id,
        format=result.format,
        family=result.family,
        bits=result.bits,
        param_count=result.param_count,
        details_patch=details_patch,
    )
