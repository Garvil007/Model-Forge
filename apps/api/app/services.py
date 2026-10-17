"""Upload policy, S3 storage wrapper, SQS enqueue, and ModelRecord->API serialization.

One module for Day 9's small set of cohesive helpers (all exist only to support the
uploads/models routers) rather than a deep services/ package — see coding-style.md on not
splitting before the repetition/complexity is real.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from modelforge_catalog import OPERATIONS, stages_for_operation
from modelforge_catalog.plans import PlanLimits, limits_for
from modelforge_catalog.system_jobs import SystemJobKind
from modelforge_catalog.system_jobs import build_message as build_system_job_message
from modelforge_catalog.uploads import classify_extension
from modelforge_db.records import JobEventRecord, JobRecord, ModelRecord

from .aws import get_s3_client, get_sqs_client
from .config import Settings

_OPERATIONS_BY_ID = {op.id: op for op in OPERATIONS}

MIN_S3_PART_BYTES = 5 * 1024 * 1024
MAX_S3_PARTS = 10_000
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


class FileTooLargeError(ValueError):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"file exceeds the plan limit of {limit_bytes} bytes")
        self.limit_bytes = limit_bytes


def sanitize_filename(filename: str) -> str:
    """Basename only, normalized, control chars and anything outside [A-Za-z0-9._-]
    replaced with "_", capped at 200 chars (extension kept). Never used for display —
    the original filename is stored separately for that."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _UNSAFE_CHARS.sub("_", base).strip("._") or "file"
    return base[:200]


@dataclass(frozen=True, slots=True)
class PartPlan:
    part_size: int
    total_parts: int


def part_plan(size: int, part_size: int) -> PartPlan:
    total = max(1, -(-size // part_size))  # ceil div, at least 1 part (empty/small files)
    if total > MAX_S3_PARTS:
        part_size = -(-size // MAX_S3_PARTS)
        part_size = max(part_size, MIN_S3_PART_BYTES)
        total = max(1, -(-size // part_size))
    return PartPlan(part_size=part_size, total_parts=total)


def classify_and_enforce_size(filename: str, size: int, plan: str) -> tuple[str, str | None]:
    """Returns (kind, format_hint). Raises UnsupportedFileTypeError or FileTooLargeError."""
    kind, format_hint = classify_extension(filename)
    limits: PlanLimits = limits_for(plan)
    limit = limits.max_model_bytes if kind == "model" else limits.max_dataset_bytes
    if size > limit:
        raise FileTooLargeError(limit)
    return kind, format_hint


def build_key(user_id: str, kind: str, entity_id: str, safe_name: str) -> str:
    folder = "models" if kind == "model" else "datasets"
    return f"users/{user_id}/{folder}/{entity_id}/{safe_name}"


class StorageService:
    """Thin S3 multipart wrapper. The API never calls get_object — model bytes are only
    ever read by workers (see root CLAUDE.md)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._s3 = get_s3_client(settings)

    def create_multipart_upload(self, key: str, retention_tag: str) -> str:
        response = self._s3.create_multipart_upload(
            Bucket=self._settings.uploads_bucket,
            Key=key,
            Tagging=f"retention={retention_tag}",
        )
        return str(response["UploadId"])

    def presign_part_urls(self, key: str, s3_upload_id: str, total_parts: int) -> list[str]:
        return [
            self._s3.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self._settings.uploads_bucket,
                    "Key": key,
                    "UploadId": s3_upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=self._settings.presign_expiry_seconds,
            )
            for part_number in range(1, total_parts + 1)
        ]

    def list_parts(self, key: str, s3_upload_id: str) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "Bucket": self._settings.uploads_bucket,
            "Key": key,
            "UploadId": s3_upload_id,
        }
        while True:
            response = self._s3.list_parts(**kwargs)
            parts.extend(response.get("Parts", []))
            if not response.get("IsTruncated"):
                return parts
            kwargs["PartNumberMarker"] = response["NextPartNumberMarker"]

    def complete(self, key: str, s3_upload_id: str, parts: list[dict[str, Any]]) -> int:
        self._s3.complete_multipart_upload(
            Bucket=self._settings.uploads_bucket,
            Key=key,
            UploadId=s3_upload_id,
            MultipartUpload={
                "Parts": [{"ETag": p["ETag"], "PartNumber": p["PartNumber"]} for p in parts]
            },
        )
        head = self._s3.head_object(Bucket=self._settings.uploads_bucket, Key=key)
        return int(head["ContentLength"])

    def abort(self, key: str, s3_upload_id: str) -> None:
        self._s3.abort_multipart_upload(
            Bucket=self._settings.uploads_bucket, Key=key, UploadId=s3_upload_id
        )

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._settings.uploads_bucket, Key=key)

    def presign_download(self, bucket: str, key: str, *, expires_in: int) -> str:
        return str(
            self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        )


class JobQueueService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sqs = get_sqs_client(settings)

    def enqueue(self, kind: SystemJobKind, *, user_id: str, model_id: str) -> None:
        self._sqs.send_message(
            QueueUrl=self._settings.system_jobs_queue_url,
            MessageBody=build_system_job_message(kind, user_id=user_id, model_id=model_id),
        )

    def enqueue_job(self, message: str, *, queue: Literal["cpu", "gpu"]) -> None:
        queue_url = (
            self._settings.cpu_jobs_queue_url
            if queue == "cpu"
            else self._settings.gpu_jobs_queue_url
        )
        self._sqs.send_message(QueueUrl=queue_url, MessageBody=message)


def serialize_model(record: ModelRecord) -> dict[str, Any]:
    details = record.details or {}
    return {
        "id": record.model_id,
        "filename": details.get("originalFilename", record.filename),
        "format": record.format,
        "family": record.family,
        "bits": record.bits,
        "params": record.param_count,
        "size": record.size_bytes,
        "inputs": details.get("inputs"),
        "metric": details.get("metric"),
        "validationFilename": details.get("validationFilename"),
        "source": details.get("source", "upload"),
        "repoId": details.get("repoId"),
        "createdAt": record.created_at,
        "status": record.status,
        "detectionError": details.get("detectionError"),
    }


def _stage_dicts(record: JobRecord, events: list[JobEventRecord]) -> list[dict[str, Any]]:
    """Reconstruct ApiJob's `stages: JobStage[]` from the operation's stage list plus the
    events actually written so far — the real-job equivalent of the mock's time-driven
    `buildStages`, but driven by what the worker reported."""
    operation = _OPERATIONS_BY_ID.get(record.operation_id)
    if operation is None:
        return []
    defs = stages_for_operation(operation, record.params)

    event_counts_by_stage: dict[str, int] = {}
    last_matched_index: int | None = None
    for event in events:
        for index, stage_def in enumerate(defs):
            if stage_def.label == event.stage:
                event_counts_by_stage[stage_def.label] = (
                    event_counts_by_stage.get(stage_def.label, 0) + 1
                )
                if last_matched_index is None or index >= last_matched_index:
                    last_matched_index = index
                break

    terminal_done = record.status == "succeeded"
    stages: list[dict[str, Any]] = []
    for index, stage_def in enumerate(defs):
        if last_matched_index is None:
            stage_status = "pending"
        elif index < last_matched_index or (index == last_matched_index and terminal_done):
            stage_status = "done"
        elif index == last_matched_index:
            stage_status = "active"
        else:
            stage_status = "pending"

        stage: dict[str, Any] = {"label": stage_def.label, "status": stage_status}
        if stage_def.epochs is not None:
            stage["totalEpochs"] = stage_def.epochs
            stage["epoch"] = min(event_counts_by_stage.get(stage_def.label, 0), stage_def.epochs)
        stages.append(stage)
    return stages


def serialize_job(record: JobRecord, events: list[JobEventRecord]) -> dict[str, Any]:
    return {
        "id": record.job_id,
        "modelId": record.model_id,
        "operationId": record.operation_id,
        "values": record.params,
        "status": record.status,
        "stages": _stage_dicts(record, events),
        "createdAt": record.created_at,
        "result": record.result,
        "error": record.error,
    }
