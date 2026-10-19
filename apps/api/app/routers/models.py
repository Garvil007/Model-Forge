"""GET /models, GET /models/{id}, POST /models/import-hf.

Contract matches apps/web/src/api/types.ts (ApiModel, ImportHfRequest) and the day-4 mock.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from modelforge_catalog.plans import limits_for
from modelforge_db.encryption import KmsEncryptor
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import UserRecord
from modelforge_db.repositories.base import new_id
from modelforge_db.repositories.datasets import DatasetRepository
from modelforge_db.repositories.models import ModelRepository
from modelforge_db.repositories.users import UserRepository
from modelforge_db.ttl import retention_seconds
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic.alias_generators import to_camel

from ..auth import current_user
from ..config import Settings, get_settings
from ..errors import ApiError
from ..huggingface import (
    HfHubService,
    HfRepoGatedError,
    HfRepoNotFoundError,
    HfUnavailableError,
    HfUnsupportedRepoError,
)
from ..services import JobQueueService, serialize_model

router = APIRouter(prefix="/models", tags=["models"])

_REPO_ID_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImportHfRequest(_Camel):
    repo_id: str = Field(pattern=_REPO_ID_RE.pattern, max_length=96)
    token: SecretStr | None = None


class PreprocessConfig(_Camel):
    input_size: int | None = None
    mean: list[float] | None = None
    std: list[float] | None = None
    channel_order: str | None = None
    layout: str | None = None


class UpdateValidationRequest(_Camel):
    dataset_id: str = Field(min_length=1)
    task_type: Literal["image_cls", "detection", "text_cls", "lm"]
    preprocess: PreprocessConfig | None = None


def get_model_repository() -> ModelRepository:
    return ModelRepository()


def get_dataset_repository() -> DatasetRepository:
    return DatasetRepository()


def get_user_repository() -> UserRepository:
    return UserRepository()


def get_hf_service(settings: Settings = Depends(get_settings)) -> HfHubService:  # noqa: B008
    return HfHubService(settings)


def get_job_queue(settings: Settings = Depends(get_settings)) -> JobQueueService:  # noqa: B008
    return JobQueueService(settings)


@router.get("")
def list_models(
    user: Annotated[UserRecord, Depends(current_user)],
    models: Annotated[ModelRepository, Depends(get_model_repository)],
) -> list[dict[str, Any]]:
    return [serialize_model(record) for record in models.list_for_user(user.user_id)]


@router.get("/{model_id}")
def get_model(
    model_id: str,
    user: Annotated[UserRecord, Depends(current_user)],
    models: Annotated[ModelRepository, Depends(get_model_repository)],
) -> dict[str, Any]:
    try:
        return serialize_model(models.get(user.user_id, model_id))
    except NotFoundError as error:
        raise ApiError(404, "model_not_found", str(error)) from error


@router.patch("/{model_id}/validation")
def set_validation_dataset(
    model_id: str,
    body: UpdateValidationRequest,
    user: Annotated[UserRecord, Depends(current_user)],
    models: Annotated[ModelRepository, Depends(get_model_repository)],
    datasets: Annotated[DatasetRepository, Depends(get_dataset_repository)],
) -> dict[str, Any]:
    try:
        models.get(user.user_id, model_id)
    except NotFoundError as error:
        raise ApiError(404, "model_not_found", str(error)) from error

    try:
        dataset = datasets.get(user.user_id, body.dataset_id)
    except NotFoundError as error:
        raise ApiError(404, "dataset_not_found", str(error)) from error

    if dataset.kind != "dataset":
        raise ApiError(
            400, "invalid_dataset_kind", f"dataset {body.dataset_id!r} is not a dataset upload"
        )

    preprocess = (
        body.preprocess.model_dump(by_alias=True, exclude_none=True) if body.preprocess else {}
    )
    updated = models.update_validation(
        user.user_id,
        model_id,
        validation_dataset_id=body.dataset_id,
        validation_filename=dataset.filename,
        task_type=body.task_type,
        preprocess=preprocess,
    )
    return serialize_model(updated)


@router.post("/import-hf", status_code=201)
def import_hf(
    body: ImportHfRequest,
    user: Annotated[UserRecord, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    models: Annotated[ModelRepository, Depends(get_model_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    hf: Annotated[HfHubService, Depends(get_hf_service)],
    job_queue: Annotated[JobQueueService, Depends(get_job_queue)],
) -> dict[str, Any]:
    token = body.token.get_secret_value() if body.token else None
    try:
        estimate = hf.estimate(body.repo_id, token)
    except HfRepoNotFoundError as error:
        raise ApiError(404, "repo_not_found", f"No repository {body.repo_id!r} was found.") from error
    except HfRepoGatedError as error:
        raise ApiError(403, "gated_repo", "This repository is gated.") from error
    except HfUnsupportedRepoError as error:
        raise ApiError(400, "unsupported_repo", "No supported weight files were found.") from error
    except HfUnavailableError as error:
        raise ApiError(502, "hf_unavailable", str(error)) from error

    limit = limits_for(user.plan).max_model_bytes
    if estimate.total_size_bytes > limit:
        raise ApiError(413, "file_too_large", f"repo exceeds the plan limit of {limit} bytes")

    if token:
        users.set_hf_token(user.user_id, token, KmsEncryptor(settings.hf_token_kms_key_id))

    model_id = new_id()
    record = models.create(
        user.user_id,
        model_id=model_id,
        filename=body.repo_id.rsplit("/", 1)[-1],
        s3_key="",
        size_bytes=estimate.total_size_bytes,
        format="torch",
        family="llm",
        bits=16,
        param_count=None,
        details={
            "source": "huggingface",
            "repoId": body.repo_id,
            "hfSelectedFiles": estimate.selected_files,
            "provisional": True,
        },
        status="importing",
        ttl_seconds=retention_seconds(limits_for(user.plan).retention_days),
    )
    job_queue.enqueue("import_hf", user_id=user.user_id, model_id=model_id)
    return serialize_model(record)
