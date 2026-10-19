"""POST /uploads/{id}/complete — fakes for every repo/queue/storage dependency, no AWS needed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import DatasetRecord, ModelRecord, UploadRecord, UserRecord

from app.auth import current_user
from app.main import app
from app.routers import uploads as uploads_router

client = TestClient(app)

_USER = UserRecord(
    user_id="user-1",
    email="user@example.com",
    plan="free",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
)


def _upload_record(**overrides: Any) -> UploadRecord:
    base = dict(
        user_id="user-1",
        upload_id="upload-1",
        kind="dataset",
        entity_id="entity-1",
        filename="calib.npz",
        safe_name="calib.npz",
        s3_key="users/user-1/datasets/entity-1/calib.npz",
        s3_upload_id="s3-upload-1",
        declared_size=1_000,
        part_size=1_000,
        total_parts=1,
        status="pending",
        retention_tag="7d",
        created_at=datetime.now(UTC).isoformat(),
        ttl=0,
    )
    base.update(overrides)
    return UploadRecord(**base)  # type: ignore[arg-type]


class _FakeUploadRepository:
    def __init__(self) -> None:
        self.uploads: dict[tuple[str, str], UploadRecord] = {}

    def seed(self, record: UploadRecord) -> None:
        self.uploads[(record.user_id, record.upload_id)] = record

    def get(self, user_id: str, upload_id: str) -> UploadRecord:
        try:
            return self.uploads[(user_id, upload_id)]
        except KeyError:
            raise NotFoundError(f"upload {upload_id!r} not found") from None

    def mark_completed(self, user_id: str, upload_id: str) -> UploadRecord:
        record = self.get(user_id, upload_id)
        updated = UploadRecord(**{**record.__dict__, "status": "completed"})
        self.uploads[(user_id, upload_id)] = updated
        return updated


class _FakeModelRepository:
    def __init__(self) -> None:
        self.models: dict[tuple[str, str], ModelRecord] = {}

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        try:
            return self.models[(user_id, model_id)]
        except KeyError:
            raise NotFoundError(f"model {model_id!r} not found") from None

    def create(self, user_id: str, **kwargs: Any) -> ModelRecord:
        model_id = kwargs.pop("model_id")
        now = datetime.now(UTC).isoformat()
        record = ModelRecord(
            user_id=user_id,
            model_id=model_id,
            filename=kwargs["filename"],
            s3_key=kwargs["s3_key"],
            size_bytes=kwargs["size_bytes"],
            format=kwargs["format"],
            family=kwargs["family"],
            bits=kwargs.get("bits"),
            param_count=kwargs.get("param_count"),
            details=kwargs.get("details") or {},
            status=kwargs.get("status", "ready"),
            created_at=now,
            updated_at=now,
            ttl=0,
        )
        self.models[(user_id, model_id)] = record
        return record

    def mark_failed(self, user_id: str, model_id: str, *, code: str, message: str) -> None:
        pass


class _FakeDatasetRepository:
    def __init__(self) -> None:
        self.datasets: dict[tuple[str, str], DatasetRecord] = {}

    def get(self, user_id: str, dataset_id: str) -> DatasetRecord:
        try:
            return self.datasets[(user_id, dataset_id)]
        except KeyError:
            raise NotFoundError(f"dataset {dataset_id!r} not found") from None

    def create(self, user_id: str, **kwargs: Any) -> DatasetRecord:
        dataset_id = kwargs.get("dataset_id") or "generated-dataset-id"
        record = DatasetRecord(
            user_id=user_id,
            dataset_id=dataset_id,
            kind=kwargs["kind"],
            filename=kwargs["filename"],
            s3_key=kwargs["s3_key"],
            size_bytes=kwargs["size_bytes"],
            model_id=kwargs.get("model_id"),
            created_at=datetime.now(UTC).isoformat(),
            ttl=0,
        )
        self.datasets[(user_id, dataset_id)] = record
        return record


class _FakeStorageService:
    def __init__(self) -> None:
        self.aborted: list[str] = []

    def list_parts(self, key: str, s3_upload_id: str) -> list[dict[str, Any]]:
        return [{"PartNumber": 1, "Size": 1_000, "ETag": "etag-1"}]

    def complete(self, key: str, s3_upload_id: str, parts: list[dict[str, Any]]) -> int:
        return 1_000

    def abort(self, key: str, s3_upload_id: str) -> None:
        self.aborted.append(key)


class _FakeJobQueue:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def enqueue(self, kind: str, *, user_id: str, model_id: str) -> None:
        self.sent.append((kind, model_id))


@pytest.fixture
def fakes() -> Any:
    upload_repo = _FakeUploadRepository()
    model_repo = _FakeModelRepository()
    dataset_repo = _FakeDatasetRepository()
    storage = _FakeStorageService()
    job_queue = _FakeJobQueue()

    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[uploads_router.get_upload_repository] = lambda: upload_repo
    app.dependency_overrides[uploads_router.get_model_repository] = lambda: model_repo
    app.dependency_overrides[uploads_router.get_dataset_repository] = lambda: dataset_repo
    app.dependency_overrides[uploads_router.get_storage_service] = lambda: storage
    app.dependency_overrides[uploads_router.get_job_queue] = lambda: job_queue

    yield {
        "uploads": upload_repo,
        "models": model_repo,
        "datasets": dataset_repo,
        "storage": storage,
        "queue": job_queue,
    }
    app.dependency_overrides.clear()


def _complete_body(filename: str = "calib.npz") -> dict[str, Any]:
    return {
        "uploadId": "upload-1",
        "model": {
            "filename": filename,
            "format": "",
            "family": "",
            "bits": 0,
            "params": 0,
            "size": 1_000,
        },
    }


def test_complete_dataset_upload_persists_dataset_record(fakes: Any) -> None:
    fakes["uploads"].seed(_upload_record())

    response = client.post("/uploads/upload-1/complete", json=_complete_body())

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": "entity-1",
        "filename": "calib.npz",
        "size": 1_000,
        "kind": "dataset",
        "createdAt": body["createdAt"],
    }

    stored = fakes["datasets"].get("user-1", "entity-1")
    assert stored.filename == "calib.npz"
    assert stored.s3_key == "users/user-1/datasets/entity-1/calib.npz"
    assert stored.size_bytes == 1_000
    assert stored.model_id is None
    assert stored.kind == "dataset"


def test_complete_dataset_upload_is_idempotent_on_retry(fakes: Any) -> None:
    fakes["uploads"].seed(_upload_record(status="completed"))
    fakes["datasets"].datasets[("user-1", "entity-1")] = DatasetRecord(
        user_id="user-1",
        dataset_id="entity-1",
        kind="dataset",
        filename="calib.npz",
        s3_key="users/user-1/datasets/entity-1/calib.npz",
        size_bytes=1_000,
        model_id=None,
        created_at="2026-01-01T00:00:00Z",
        ttl=0,
    )

    response = client.post("/uploads/upload-1/complete", json=_complete_body())

    assert response.status_code == 201
    assert response.json()["id"] == "entity-1"


def test_complete_model_upload_still_returns_model(fakes: Any) -> None:
    fakes["uploads"].seed(
        _upload_record(
            kind="model",
            entity_id="model-1",
            s3_key="users/user-1/models/model-1/model.onnx",
            safe_name="model.onnx",
            filename="model.onnx",
        )
    )

    response = client.post(
        "/uploads/upload-1/complete",
        json={
            "uploadId": "upload-1",
            "model": {
                "filename": "model.onnx",
                "format": "onnx",
                "family": "resnet",
                "bits": 32,
                "params": 1_000,
                "size": 1_000,
                "inputs": None,
                "metric": None,
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "model-1"
    assert fakes["queue"].sent == [("detect_format", "model-1")]
