"""TTL attributes are set on creation so DynamoDB's native sweep can expire old items."""

from __future__ import annotations

import time
from typing import Any

from modelforge_db import JobEventRepository, JobRepository, ModelRepository
from modelforge_db.ttl import (
    JOB_EVENT_RETENTION_SECONDS,
    JOB_RETENTION_SECONDS,
    MODEL_RETENTION_SECONDS,
)

from .conftest import unique_id

_TOLERANCE_SECONDS = 30


def test_model_ttl_matches_retention_window(table: Any) -> None:
    repo = ModelRepository(table)
    before = time.time()
    model = repo.create(
        unique_id(), filename="a.onnx", s3_key="a", size_bytes=1, format="onnx", family="x"
    )

    assert abs(model.ttl - (before + MODEL_RETENTION_SECONDS)) < _TOLERANCE_SECONDS


def test_job_ttl_matches_retention_window(table: Any) -> None:
    repo = JobRepository(table)
    before = time.time()
    job = repo.create(unique_id(), operation_id="op.a", params={}, queue="cpu")

    assert abs(job.ttl - (before + JOB_RETENTION_SECONDS)) < _TOLERANCE_SECONDS


def test_job_event_ttl_matches_retention_window(table: Any) -> None:
    jobs = JobRepository(table)
    events = JobEventRepository(table)
    user_id = unique_id()
    job = jobs.create(user_id, operation_id="op.a", params={}, queue="cpu")

    before = time.time()
    event = events.append(user_id, job.job_id, stage="upload", message="uploading")

    assert abs(event.ttl - (before + JOB_EVENT_RETENTION_SECONDS)) < _TOLERANCE_SECONDS
