"""POST /jobs, GET /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel, GET /jobs/{id}/download.

Contract matches apps/web/src/api/types.ts (ApiJob, CreateJobRequest) and the Day 5 mock
(apps/web/src/mocks/handlers.ts) exactly, so the frontend needs no changes beyond swapping
its API base URL. Sync `def` handlers on purpose — see uploads.py's docstring.
"""

from __future__ import annotations

from typing import Annotated, Any

import jsonschema
from fastapi import APIRouter, Depends
from modelforge_catalog import OPERATIONS, check_availability
from modelforge_catalog.export import build_param_schema
from modelforge_catalog.job_messages import build_message as build_job_message
from modelforge_catalog.models import ModelInfo, OperationSpec
from modelforge_catalog.plans import limits_for
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import UserRecord
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository
from modelforge_db.repositories.usage import UsageRepository
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ..auth import current_user
from ..config import Settings, get_settings
from ..errors import ApiError
from ..services import JobQueueService, StorageService, serialize_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

_OPERATIONS_BY_ID: dict[str, OperationSpec] = {op.id: op for op in OPERATIONS}
_ACTIVE_STATUSES = ("queued", "running")


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateJobRequest(_Camel):
    model_id: str
    operation_id: str
    values: dict[str, Any] = {}


def get_job_repository() -> JobRepository:
    return JobRepository()


def get_job_event_repository() -> JobEventRepository:
    return JobEventRepository()


def get_model_repository() -> ModelRepository:
    return ModelRepository()


def get_usage_repository() -> UsageRepository:
    return UsageRepository()


def get_job_queue(settings: Settings = Depends(get_settings)) -> JobQueueService:  # noqa: B008
    return JobQueueService(settings)


def get_storage_service(settings: Settings = Depends(get_settings)) -> StorageService:  # noqa: B008
    return StorageService(settings)


def _current_year_month() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m")


def _model_info(record: Any) -> ModelInfo:
    return ModelInfo(
        format=record.format,
        family=record.family,
        bits=record.bits or 0.0,
        params=float(record.param_count or 0),
        size=record.size_bytes,
    )


@router.post("", status_code=201)
def create_job(
    body: CreateJobRequest,
    user: Annotated[UserRecord, Depends(current_user)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    models: Annotated[ModelRepository, Depends(get_model_repository)],
    usage: Annotated[UsageRepository, Depends(get_usage_repository)],
    job_queue: Annotated[JobQueueService, Depends(get_job_queue)],
) -> dict[str, Any]:
    operation = _OPERATIONS_BY_ID.get(body.operation_id)
    if operation is None:
        raise ApiError(404, "operation_not_found", f"No operation {body.operation_id!r}.")

    try:
        model = models.get(user.user_id, body.model_id)
    except NotFoundError as error:
        raise ApiError(404, "model_not_found", str(error)) from error

    try:
        jsonschema.validate(body.values, build_param_schema(operation))
    except jsonschema.ValidationError as error:
        raise ApiError(400, "invalid_params", error.message) from error

    availability = check_availability(operation, _model_info(model))
    if not availability.ok:
        raise ApiError(
            400, "operation_unavailable", availability.why or "This operation isn't available."
        )

    max_concurrent = limits_for(user.plan).max_concurrent_jobs
    active_jobs = [j for j in jobs.list_for_user(user.user_id) if j.status in _ACTIVE_STATUSES]
    if len(active_jobs) >= max_concurrent:
        raise ApiError(
            429,
            "quota_exceeded",
            f"You already have {len(active_jobs)} jobs running or queued "
            f"(limit for your plan is {max_concurrent}).",
        )

    record = jobs.create(
        user.user_id,
        operation_id=operation.id,
        params=body.values,
        queue=operation.queue,
        model_id=body.model_id,
    )
    usage.increment(user.user_id, _current_year_month(), jobs_run=1)

    message = build_job_message(
        job_id=record.job_id,
        user_id=user.user_id,
        model_id=body.model_id,
        operation_id=operation.id,
    )
    job_queue.enqueue_job(message, queue=operation.queue)

    return serialize_job(record, [])


@router.get("")
def list_jobs(
    user: Annotated[UserRecord, Depends(current_user)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
) -> list[dict[str, Any]]:
    return [serialize_job(record, []) for record in jobs.list_for_user(user.user_id)]


@router.get("/{job_id}")
def get_job(
    job_id: str,
    user: Annotated[UserRecord, Depends(current_user)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    job_events: Annotated[JobEventRepository, Depends(get_job_event_repository)],
) -> dict[str, Any]:
    try:
        record = jobs.get(user.user_id, job_id)
    except NotFoundError as error:
        raise ApiError(404, "job_not_found", str(error)) from error
    events = job_events.list_for_job(user.user_id, job_id)
    return serialize_job(record, events)


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    user: Annotated[UserRecord, Depends(current_user)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    job_events: Annotated[JobEventRepository, Depends(get_job_event_repository)],
) -> dict[str, Any]:
    try:
        record = jobs.get(user.user_id, job_id)
    except NotFoundError as error:
        raise ApiError(404, "job_not_found", str(error)) from error

    if record.status not in _ACTIVE_STATUSES:
        events = job_events.list_for_job(user.user_id, job_id)
        return serialize_job(record, events)

    # Queued jobs are simply marked canceled (the worker's idempotency check drops the SQS
    # message when it's eventually delivered). Running jobs are marked canceled here too; the
    # worker checks this flag between stages and stops. Terminating an in-flight Batch job via
    # `batch_job_id` is wired in once the dispatcher exists (Step E) — TODO(step-e).
    updated = jobs.update_progress(
        user.user_id, job_id, status="canceled", progress_percent=record.progress_percent
    )
    events = job_events.list_for_job(user.user_id, job_id)
    return serialize_job(updated, events)


@router.get("/{job_id}/download")
def download_job(
    job_id: str,
    user: Annotated[UserRecord, Depends(current_user)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> dict[str, str]:
    try:
        record = jobs.get(user.user_id, job_id)
    except NotFoundError as error:
        raise ApiError(404, "job_not_found", str(error)) from error

    if record.status != "succeeded" or not record.result or "s3Key" not in record.result:
        raise ApiError(404, "result_not_available", "This job has no downloadable result.")

    url = storage.presign_download(
        settings.results_bucket,
        record.result["s3Key"],
        expires_in=settings.download_presign_expiry_seconds,
    )
    return {"url": url}
