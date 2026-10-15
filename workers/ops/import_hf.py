"""Handles an `import_hf` SystemJobMessage: download the selected repo files, re-upload
them to S3 under the user's model key, then run the same detection as a direct upload.

Never imports transformers or calls `trust_remote_code` — only `huggingface_hub`'s plain
file download is used, so no repo-provided Python ever runs.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import boto3
from huggingface_hub import hf_hub_download
from modelforge_db.encryption import KmsEncryptor
from modelforge_db.exceptions import NotFoundError
from modelforge_db.repositories.models import ModelRepository
from modelforge_db.repositories.users import UserRepository

from core.s3_reader import S3RangeReader

from .detect import DetectionError, sniff_and_detect

_PART_SIZE = 100 * 1024 * 1024


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def _upload_file(s3: Any, bucket: str, key: str, local_path: Path, retention_tag: str) -> None:
    s3.upload_file(
        str(local_path), bucket, key, ExtraArgs={"Tagging": f"retention={retention_tag}"}
    )


def handle_import_hf(*, user_id: str, model_id: str) -> None:
    models = ModelRepository()
    users = UserRepository()
    try:
        record = models.get(user_id, model_id)
    except NotFoundError:
        return
    if record.status != "importing":
        return

    repo_id = record.details.get("repoId")
    selected_files: list[str] = record.details.get("hfSelectedFiles", [])
    if not repo_id or not selected_files:
        models.mark_failed(user_id, model_id, code="unsupported_repo", message="no files selected")
        return

    token = users.get_hf_token(
        user_id, KmsEncryptor(os.environ.get("MF_HF_TOKEN_KMS_KEY_ID", "alias/modelforge-hf-tokens"))
    )

    bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    s3 = _s3_client()
    retention_tag = record.details.get("retentionTag", "7d")
    weight_file = next((f for f in selected_files if not f.endswith(".json")), selected_files[0])
    key = f"users/{user_id}/models/{model_id}/{Path(weight_file).name}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            local_path = Path(
                hf_hub_download(repo_id=repo_id, filename=weight_file, token=token, cache_dir=tmp_dir)
            )
            total_size = local_path.stat().st_size
            _upload_file(s3, bucket, key, local_path, retention_tag)

            models.update_status(user_id, model_id, "checking")
            reader = S3RangeReader(s3, bucket, key, total_size)
            probe = (
                reader.read_all(512 * 1024 * 1024)
                if total_size <= 512 * 1024 * 1024
                else reader.read(8 * 1024 * 1024)
            )
            result = sniff_and_detect(probe, total_size, None)
        except DetectionError as error:
            models.mark_failed(user_id, model_id, code=error.code, message=str(error))
            return
        except Exception as error:  # noqa: BLE001 — download/network failures are terminal here
            models.mark_failed(user_id, model_id, code="hf_download_failed", message=str(error))
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
        expected_status="checking",
    )
