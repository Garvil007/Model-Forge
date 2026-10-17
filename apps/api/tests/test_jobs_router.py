"""POST/GET /jobs, cancel, download — fakes for every repo/queue dependency, no AWS needed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from modelforge_catalog.job_messages import parse_message
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import JobEventRecord, JobRecord, ModelRecord, UserRecord

from app.auth import current_user
from app.main import app
from app.routers import jobs as jobs_router

client = TestClient(app)

_USER = UserRecord(
    user_id="user-1",
    email="user@example.com",
    plan="free",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
)


class _FakeJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[tuple[str, str], JobRecord] = {}

    def create(
        self,
        user_id: str,
        *,
        operation_id: str,
        params: dict[str, Any],
        queue: str,
        model_id: str | None = None,
        cost_estimate: float | None = None,
    ) -> JobRecord:
        job_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        record = JobRecord(
            user_id=user_id,
            job_id=job_id,
            operation_id=operation_id,
            params=params,
            queue=queue,
            status="queued",
            progress_percent=0,
            result=None,
            error=None,
            timings={},
            cost_estimate=cost_estimate,
            model_id=model_id,
            created_at=now,
            updated_at=now,
            ttl=0,
        )
        self.jobs[(user_id, job_id)] = record
        return record

    def get(self, user_id: str, job_id: str) -> JobRecord:
        try:
            return self.jobs[(user_id, job_id)]
        except KeyError:
            raise NotFoundError(f"job {job_id!r} not found") from None

    def list_for_user(self, user_id: str, *, limit: int = 50) -> list[JobRecord]:
        return [r for (u, _), r in self.jobs.items() if u == user_id][:limit]

    def update_progress(
        self,
        user_id: str,
        job_id: str,
        *,
        status: str,
        progress_percent: int,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        timings: dict[str, Any] | None = None,
    ) -> JobRecord:
        record = self.get(user_id, job_id)
        updated = JobRecord(
            **{
                **record.__dict__,
                "status": status,
                "progress_percent": progress_percent,
                "result": result,
                "error": error,
                "timings": timings or record.timings,
            }
        )
        self.jobs[(user_id, job_id)] = updated
        return updated

    def set_result(self, user_id: str, job_id: str, record: JobRecord) -> None:
        self.jobs[(user_id, job_id)] = record


class _FakeJobEventRepository:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], list[JobEventRecord]] = {}

    def append(
        self, user_id: str, job_id: str, *, stage: str, message: str, percent: int | None = None
    ) -> JobEventRecord:
        event = JobEventRecord(
            user_id=user_id,
            job_id=job_id,
            stage=stage,
            message=message,
            percent=percent,
            timestamp_ms=len(self.events.get((user_id, job_id), [])),
            ttl=0,
        )
        self.events.setdefault((user_id, job_id), []).append(event)
        return event

    def list_for_job(self, user_id: str, job_id: str, *, limit: int = 200) -> list[JobEventRecord]:
        return self.events.get((user_id, job_id), [])[:limit]


class _FakeModelRepository:
    def __init__(self) -> None:
        self.models: dict[tuple[str, str], ModelRecord] = {}

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        try:
            return self.models[(user_id, model_id)]
        except KeyError:
            raise NotFoundError(f"model {model_id!r} not found") from None


class _FakeUsageRepository:
    def __init__(self) -> None:
        self.increments: list[dict[str, Any]] = []

    def increment(self, user_id: str, year_month: str, *, jobs_run: int = 0, **_: Any) -> None:
        self.increments.append({"userId": user_id, "yearMonth": year_month, "jobsRun": jobs_run})


class _FakeJobQueue:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def enqueue_job(self, message: str, *, queue: str) -> None:
        self.sent.append((message, queue))


def _model_record(**overrides: Any) -> ModelRecord:
    base = dict(
        user_id="user-1",
        model_id="model-1",
        filename="model.onnx",
        s3_key="users/user-1/models/model-1/model.onnx",
        size_bytes=4_000_000,
        format="onnx",
        family="vision",
        bits=32.0,
        param_count=1_000_000,
        details={},
        status="ready",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        ttl=0,
    )
    base.update(overrides)
    return ModelRecord(**base)  # type: ignore[arg-type]


@pytest.fixture
def fakes() -> Any:
    job_repo = _FakeJobRepository()
    job_events = _FakeJobEventRepository()
    model_repo = _FakeModelRepository()
    usage_repo = _FakeUsageRepository()
    job_queue = _FakeJobQueue()

    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[jobs_router.get_job_repository] = lambda: job_repo
    app.dependency_overrides[jobs_router.get_job_event_repository] = lambda: job_events
    app.dependency_overrides[jobs_router.get_model_repository] = lambda: model_repo
    app.dependency_overrides[jobs_router.get_usage_repository] = lambda: usage_repo
    app.dependency_overrides[jobs_router.get_job_queue] = lambda: job_queue

    yield {
        "jobs": job_repo,
        "events": job_events,
        "models": model_repo,
        "usage": usage_repo,
        "queue": job_queue,
    }
    app.dependency_overrides.clear()


def test_create_job_rejects_unknown_operation(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    response = client.post(
        "/jobs", json={"modelId": "model-1", "operationId": "nope", "values": {}}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "operation_not_found"


def test_create_job_rejects_unknown_model(fakes: Any) -> None:
    response = client.post(
        "/jobs", json={"modelId": "missing", "operationId": "q_int8_dyn", "values": {}}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_create_job_rejects_invalid_params(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record(format="torch")
    response = client.post(
        "/jobs",
        json={
            "modelId": "model-1",
            "operationId": "p_magnitude",
            "values": {"sparsity": 999},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_params"


def test_create_job_rejects_unavailable_operation(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record(format="gguf")
    response = client.post(
        "/jobs", json={"modelId": "model-1", "operationId": "q_int8_dyn", "values": {}}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "operation_unavailable"


def test_create_job_enforces_quota(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    for _ in range(2):  # free plan's max_concurrent_jobs
        fakes["jobs"].create(
            "user-1", operation_id="q_int8_dyn", params={}, queue="cpu", model_id="model-1"
        )
    response = client.post(
        "/jobs", json={"modelId": "model-1", "operationId": "q_int8_dyn", "values": {}}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_exceeded"


def test_create_job_happy_path_enqueues_and_increments_usage(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    response = client.post(
        "/jobs", json={"modelId": "model-1", "operationId": "q_int8_dyn", "values": {}}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["modelId"] == "model-1"
    assert body["operationId"] == "q_int8_dyn"
    assert body["status"] == "queued"
    assert body["stages"] == [
        {"label": "Loading model", "status": "pending"},
        {"label": "Quantizing weights", "status": "pending"},
        {"label": "Measuring accuracy", "status": "pending"},
    ]

    assert len(fakes["queue"].sent) == 1
    message, queue = fakes["queue"].sent[0]
    assert queue == "cpu"
    parsed = parse_message(message)
    assert parsed.job_id == body["id"]
    assert parsed.user_id == "user-1"
    assert parsed.model_id == "model-1"
    assert parsed.operation_id == "q_int8_dyn"

    assert fakes["usage"].increments == [
        {"userId": "user-1", "yearMonth": fakes["usage"].increments[0]["yearMonth"], "jobsRun": 1}
    ]


def test_get_job_reconstructs_stages_from_events(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    record = fakes["jobs"].create(
        "user-1", operation_id="q_int8_dyn", params={}, queue="cpu", model_id="model-1"
    )
    fakes["events"].append("user-1", record.job_id, stage="Loading model", message="...")
    fakes["events"].append("user-1", record.job_id, stage="Quantizing weights", message="...")

    response = client.get(f"/jobs/{record.job_id}")
    assert response.status_code == 200
    stages = response.json()["stages"]
    assert stages[0] == {"label": "Loading model", "status": "done"}
    assert stages[1] == {"label": "Quantizing weights", "status": "active"}
    assert stages[2] == {"label": "Measuring accuracy", "status": "pending"}


def test_get_job_marks_all_stages_done_when_succeeded(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    record = fakes["jobs"].create(
        "user-1", operation_id="q_int8_dyn", params={}, queue="cpu", model_id="model-1"
    )
    fakes["events"].append("user-1", record.job_id, stage="Measuring accuracy", message="...")
    fakes["jobs"].update_progress(
        "user-1", record.job_id, status="succeeded", progress_percent=100
    )

    response = client.get(f"/jobs/{record.job_id}")
    stages = response.json()["stages"]
    assert all(stage["status"] == "done" for stage in stages)


def test_get_job_404_for_missing_job(fakes: Any) -> None:
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_cancel_queued_job_marks_canceled(fakes: Any) -> None:
    record = fakes["jobs"].create("user-1", operation_id="q_int8_dyn", params={}, queue="cpu")
    response = client.post(f"/jobs/{record.job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"


def test_cancel_running_job_marks_canceled_without_batch_client(fakes: Any) -> None:
    record = fakes["jobs"].create("user-1", operation_id="q_int8_dyn", params={}, queue="cpu")
    fakes["jobs"].update_progress("user-1", record.job_id, status="running", progress_percent=10)

    response = client.post(f"/jobs/{record.job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"


def test_cancel_terminal_job_is_a_noop(fakes: Any) -> None:
    record = fakes["jobs"].create("user-1", operation_id="q_int8_dyn", params={}, queue="cpu")
    fakes["jobs"].update_progress(
        "user-1", record.job_id, status="succeeded", progress_percent=100
    )

    response = client.post(f"/jobs/{record.job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_download_404_before_success(fakes: Any) -> None:
    record = fakes["jobs"].create("user-1", operation_id="q_int8_dyn", params={}, queue="cpu")
    response = client.get(f"/jobs/{record.job_id}/download")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "result_not_available"


def test_download_returns_presigned_url_after_success(fakes: Any) -> None:
    record = fakes["jobs"].create("user-1", operation_id="q_int8_dyn", params={}, queue="cpu")
    fakes["jobs"].update_progress(
        "user-1",
        record.job_id,
        status="succeeded",
        progress_percent=100,
        result={
            "outputBytes": 100,
            "downloadName": "model.onnx",
            "s3Key": "users/user-1/results/x/model.onnx",
        },
    )

    response = client.get(f"/jobs/{record.job_id}/download")

    assert response.status_code == 200
    assert response.json()["url"].startswith("http")
