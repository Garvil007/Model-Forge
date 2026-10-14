from __future__ import annotations

from typing import Any

from modelforge_db import JobEventRepository, JobRepository, NotFoundError

from .conftest import unique_id


def test_create_and_get_job(table: Any) -> None:
    repo = JobRepository(table)
    user_id = unique_id()

    created = repo.create(
        user_id, operation_id="quantize.int8", params={"bits": 8}, queue="cpu"
    )
    fetched = repo.get(user_id, created.job_id)

    assert fetched == created
    assert fetched.status == "queued"
    assert fetched.progress_percent == 0


def test_update_progress_sets_status_result_and_error(table: Any) -> None:
    repo = JobRepository(table)
    user_id = unique_id()
    created = repo.create(user_id, operation_id="quantize.int8", params={}, queue="cpu")

    updated = repo.update_progress(
        user_id,
        created.job_id,
        status="succeeded",
        progress_percent=100,
        result={"outputSizeBytes": 512, "accuracyDelta": -0.004},
        timings={"seconds": 12.5},
    )

    assert updated.status == "succeeded"
    assert updated.progress_percent == 100
    assert updated.result == {"outputSizeBytes": 512, "accuracyDelta": -0.004}
    assert updated.timings == {"seconds": 12.5}


def test_update_progress_on_missing_job_raises_not_found(table: Any) -> None:
    repo = JobRepository(table)

    try:
        repo.update_progress(unique_id(), unique_id(), status="running", progress_percent=10)
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")


def test_list_for_user_returns_newest_first(table: Any) -> None:
    repo = JobRepository(table)
    user_id = unique_id()

    first = repo.create(user_id, operation_id="op.a", params={}, queue="cpu")
    second = repo.create(user_id, operation_id="op.b", params={}, queue="cpu")

    listed = repo.list_for_user(user_id)

    assert [job.job_id for job in listed] == [second.job_id, first.job_id]


def test_job_events_append_and_list_in_order(table: Any) -> None:
    jobs = JobRepository(table)
    events = JobEventRepository(table)
    user_id = unique_id()
    job = jobs.create(user_id, operation_id="op.a", params={}, queue="cpu")

    events.append(user_id, job.job_id, stage="upload", message="uploading", percent=10)
    events.append(user_id, job.job_id, stage="quantize", message="quantizing", percent=60)
    events.append(user_id, job.job_id, stage="done", message="finished", percent=100)

    listed = events.list_for_job(user_id, job.job_id)

    assert [event.stage for event in listed] == ["upload", "quantize", "done"]
    assert all(event.ttl > 0 for event in listed)
