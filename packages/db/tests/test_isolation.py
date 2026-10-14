"""Proves user A cannot read, list, or write user B's models or jobs.

Every repository method takes a user id as part of its key; this asserts there is no code
path that returns or mutates another user's item even when the attacker knows the exact id.
"""

from __future__ import annotations

from typing import Any

from modelforge_db import (
    JobEventRepository,
    JobRepository,
    ModelRepository,
    NotFoundError,
)

from .conftest import unique_id


def _create_model(repo: ModelRepository, owner_id: str) -> Any:
    return repo.create(
        owner_id, filename="a.onnx", s3_key="a", size_bytes=1, format="onnx", family="x"
    )


def test_user_cannot_get_another_users_model(table: Any) -> None:
    repo = ModelRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    model = _create_model(repo, owner_id)

    try:
        repo.get(attacker_id, model.model_id)
    except NotFoundError:
        pass
    else:
        raise AssertionError("attacker fetched another user's model")


def test_user_cannot_list_another_users_models(table: Any) -> None:
    repo = ModelRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    repo.create(owner_id, filename="a.onnx", s3_key="a", size_bytes=1, format="onnx", family="x")

    assert repo.list_for_user(attacker_id) == []


def test_user_cannot_update_another_users_model_status(table: Any) -> None:
    repo = ModelRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    model = _create_model(repo, owner_id)

    try:
        repo.update_status(attacker_id, model.model_id, "deleted")
    except NotFoundError:
        pass
    else:
        raise AssertionError("attacker updated another user's model")

    assert repo.get(owner_id, model.model_id).status != "deleted"


def test_user_cannot_delete_another_users_model(table: Any) -> None:
    repo = ModelRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    model = _create_model(repo, owner_id)

    repo.delete(attacker_id, model.model_id)  # no-op: wrong partition, nothing to delete

    assert repo.get(owner_id, model.model_id) == model


def test_user_cannot_get_another_users_job(table: Any) -> None:
    repo = JobRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    job = repo.create(owner_id, operation_id="op.a", params={}, queue="cpu")

    try:
        repo.get(attacker_id, job.job_id)
    except NotFoundError:
        pass
    else:
        raise AssertionError("attacker fetched another user's job")


def test_user_cannot_list_another_users_jobs(table: Any) -> None:
    repo = JobRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    repo.create(owner_id, operation_id="op.a", params={}, queue="cpu")

    assert repo.list_for_user(attacker_id) == []


def test_user_cannot_update_another_users_job_progress(table: Any) -> None:
    repo = JobRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    job = repo.create(owner_id, operation_id="op.a", params={}, queue="cpu")

    try:
        repo.update_progress(attacker_id, job.job_id, status="succeeded", progress_percent=100)
    except NotFoundError:
        pass
    else:
        raise AssertionError("attacker updated another user's job")

    assert repo.get(owner_id, job.job_id).status == "queued"


def test_user_cannot_list_another_users_job_events(table: Any) -> None:
    jobs = JobRepository(table)
    events = JobEventRepository(table)
    owner_id, attacker_id = unique_id(), unique_id()
    job = jobs.create(owner_id, operation_id="op.a", params={}, queue="cpu")
    events.append(owner_id, job.job_id, stage="upload", message="uploading")

    assert events.list_for_job(attacker_id, job.job_id) == []
