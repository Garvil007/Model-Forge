"""POST /uploads and POST /uploads/{id}/complete — direct-to-S3 multipart uploads.

Contract matches apps/web/src/api/types.ts (CreateUploadRequest/Response,
CompleteUploadRequest) and apps/web/src/mocks/handlers.ts's day-4 mock exactly, so the
frontend needs only its API base URL changed. Sync `def` handlers on purpose: boto3 has no
async client, and FastAPI runs sync handlers in its threadpool so these calls don't block
the event loop (see fastapi.md's async rule — the alternative, wrapping every boto3 call in
run_in_executor by hand, buys nothing here).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from modelforge_catalog.plans import limits_for
from modelforge_catalog.uploads import UnsupportedFileTypeError
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import UploadRecord, UserRecord
from modelforge_db.repositories.base import new_id
from modelforge_db.repositories.datasets import DatasetRepository
from modelforge_db.repositories.models import ModelRepository
from modelforge_db.repositories.uploads import UploadRepository
from modelforge_db.ttl import retention_seconds
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..auth import current_user
from ..config import Settings, get_settings
from ..errors import ApiError
from ..services import (
    FileTooLargeError,
    JobQueueService,
    StorageService,
    build_key,
    classify_and_enforce_size,
    part_plan,
    sanitize_filename,
    serialize_dataset,
    serialize_model,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateUploadRequest(_Camel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class ModelHint(_Camel):
    filename: str
    format: str
    family: str
    bits: float
    params: float
    size: int
    inputs: str | None = None
    metric: tuple[str, float, str] | None = None


class CompleteUploadRequest(_Camel):
    upload_id: str
    model: ModelHint


def get_model_repository() -> ModelRepository:
    return ModelRepository()


def get_upload_repository() -> UploadRepository:
    return UploadRepository()


def get_dataset_repository() -> DatasetRepository:
    return DatasetRepository()


def get_storage_service(settings: Settings = Depends(get_settings)) -> StorageService:  # noqa: B008
    return StorageService(settings)


def get_job_queue(settings: Settings = Depends(get_settings)) -> JobQueueService:  # noqa: B008
    return JobQueueService(settings)


def _retention_tag_for(plan: str) -> Literal["7d", "30d"]:
    return limits_for(plan).retention_tag  # type: ignore[return-value]


def _retention_days_for(plan: str) -> int:
    return limits_for(plan).retention_days


@router.post("", status_code=201)
def create_upload(
    body: CreateUploadRequest,
    user: Annotated[UserRecord, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    uploads: Annotated[UploadRepository, Depends(get_upload_repository)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> dict[str, Any]:
    try:
        kind, _format_hint = classify_and_enforce_size(body.filename, body.size, user.plan)
    except UnsupportedFileTypeError as error:
        raise ApiError(400, "unsupported_file_type", str(error)) from error
    except FileTooLargeError as error:
        raise ApiError(413, "file_too_large", str(error)) from error

    entity_id = new_id()
    safe_name = sanitize_filename(body.filename)
    key = build_key(user.user_id, kind, entity_id, safe_name)
    plan_tag = _retention_tag_for(user.plan)
    plan = part_plan(body.size, settings.upload_part_size_bytes)

    s3_upload_id = storage.create_multipart_upload(key, plan_tag)
    record = uploads.create(
        user.user_id,
        kind=kind,
        entity_id=entity_id,
        filename=body.filename,
        safe_name=safe_name,
        s3_key=key,
        s3_upload_id=s3_upload_id,
        declared_size=body.size,
        part_size=plan.part_size,
        total_parts=plan.total_parts,
        retention_tag=plan_tag,
    )
    part_urls = storage.presign_part_urls(key, s3_upload_id, plan.total_parts)
    return {
        "uploadId": record.upload_id,
        "key": key,
        "partSize": plan.part_size,
        "totalParts": plan.total_parts,
        "partUrls": part_urls,
    }


@router.post("/{upload_id}/complete", status_code=201)
def complete_upload(
    upload_id: str,
    body: CompleteUploadRequest,
    user: Annotated[UserRecord, Depends(current_user)],
    uploads: Annotated[UploadRepository, Depends(get_upload_repository)],
    models: Annotated[ModelRepository, Depends(get_model_repository)],
    datasets: Annotated[DatasetRepository, Depends(get_dataset_repository)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
    job_queue: Annotated[JobQueueService, Depends(get_job_queue)],
) -> dict[str, Any]:
    if body.upload_id != upload_id:
        raise ApiError(400, "invalid_request", "uploadId in the body must match the path")

    try:
        record = uploads.get(user.user_id, upload_id)
    except NotFoundError as error:
        raise ApiError(404, "upload_not_found", str(error)) from error

    if record.status == "completed":
        return _already_completed_response(record, user.user_id, models, datasets)

    parts = sorted(
        storage.list_parts(record.s3_key, record.s3_upload_id), key=lambda p: p["PartNumber"]
    )
    expected_numbers = list(range(1, record.total_parts + 1))
    if [p["PartNumber"] for p in parts] != expected_numbers:
        raise ApiError(
            400,
            "incomplete_upload",
            f"Only {len(parts)} of {record.total_parts} parts were received.",
        )
    for part in parts[:-1]:
        if int(part["Size"]) != record.part_size:
            storage.abort(record.s3_key, record.s3_upload_id)
            raise ApiError(400, "incomplete_upload", f"part {part['PartNumber']} has the wrong size")

    actual_size = storage.complete(record.s3_key, record.s3_upload_id, parts)
    if actual_size != record.declared_size:
        raise ApiError(
            400, "size_mismatch", f"uploaded {actual_size} bytes, declared {record.declared_size}"
        )

    uploads.mark_completed(user.user_id, upload_id)

    if record.kind == "dataset":
        dataset_record = datasets.create(
            user.user_id,
            kind="dataset",
            filename=body.model.filename,
            s3_key=record.s3_key,
            size_bytes=actual_size,
            model_id=None,
            dataset_id=record.entity_id,
        )
        return serialize_dataset(dataset_record)

    hint = body.model
    model_record = models.create(
        user.user_id,
        model_id=record.entity_id,
        filename=record.safe_name,
        s3_key=record.s3_key,
        size_bytes=actual_size,
        format=hint.format,
        family=hint.family,
        bits=hint.bits,
        param_count=int(hint.params) if hint.params else None,
        details={
            "originalFilename": record.filename,
            "source": "upload",
            "inputs": hint.inputs,
            "metric": list(hint.metric) if hint.metric else None,
            "provisional": True,
        },
        status="checking",
        ttl_seconds=retention_seconds(_retention_days_for(user.plan)),
    )
    try:
        job_queue.enqueue("detect_format", user_id=user.user_id, model_id=record.entity_id)
    except Exception as error:
        models.mark_failed(
            user.user_id, record.entity_id, code="enqueue_failed", message=str(error)
        )
        raise ApiError(503, "enqueue_failed", "Could not schedule format detection.") from error

    return serialize_model(model_record)


def _already_completed_response(
    record: UploadRecord,
    user_id: str,
    models: ModelRepository,
    datasets: DatasetRepository,
) -> dict[str, Any]:
    """A retried `complete` call for an upload that already finished — look the entity
    up by the kind recorded on the upload session rather than guessing."""
    if record.kind == "dataset":
        try:
            return serialize_dataset(datasets.get(user_id, record.entity_id))
        except NotFoundError as error:
            raise ApiError(404, "dataset_not_found", str(error)) from error
    try:
        return serialize_model(models.get(user_id, record.entity_id))
    except NotFoundError as error:
        raise ApiError(404, "model_not_found", str(error)) from error
