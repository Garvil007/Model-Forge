"""PATCH /models/{id}/validation — attach a calibration/validation dataset to a model."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from modelforge_db.exceptions import NotFoundError
from modelforge_db.records import DatasetRecord, ModelRecord, UserRecord

from app.auth import current_user
from app.main import app
from app.routers import models as models_router

client = TestClient(app)

_USER = UserRecord(
    user_id="user-1",
    email="user@example.com",
    plan="free",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
)


class _FakeModelRepository:
    def __init__(self) -> None:
        self.models: dict[tuple[str, str], ModelRecord] = {}

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        try:
            return self.models[(user_id, model_id)]
        except KeyError:
            raise NotFoundError(f"model {model_id!r} not found") from None

    def update_validation(
        self,
        user_id: str,
        model_id: str,
        *,
        validation_dataset_id: str,
        validation_filename: str,
        task_type: str,
        preprocess: dict[str, Any],
    ) -> ModelRecord:
        record = self.get(user_id, model_id)
        updated = ModelRecord(
            **{
                **record.__dict__,
                "details": {
                    **record.details,
                    "validationDatasetId": validation_dataset_id,
                    "validationFilename": validation_filename,
                    "taskType": task_type,
                    "preprocess": preprocess,
                },
            }
        )
        self.models[(user_id, model_id)] = updated
        return updated


class _FakeDatasetRepository:
    def __init__(self) -> None:
        self.datasets: dict[tuple[str, str], DatasetRecord] = {}

    def get(self, user_id: str, dataset_id: str) -> DatasetRecord:
        try:
            return self.datasets[(user_id, dataset_id)]
        except KeyError:
            raise NotFoundError(f"dataset {dataset_id!r} not found") from None


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


def _dataset_record(**overrides: Any) -> DatasetRecord:
    base = dict(
        user_id="user-1",
        dataset_id="dataset-1",
        kind="dataset",
        filename="calib.npz",
        s3_key="users/user-1/datasets/dataset-1/calib.npz",
        size_bytes=1_000,
        model_id=None,
        created_at="2026-01-01T00:00:00Z",
        ttl=0,
    )
    base.update(overrides)
    return DatasetRecord(**base)  # type: ignore[arg-type]


@pytest.fixture
def fakes() -> Any:
    model_repo = _FakeModelRepository()
    dataset_repo = _FakeDatasetRepository()

    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[models_router.get_model_repository] = lambda: model_repo
    app.dependency_overrides[models_router.get_dataset_repository] = lambda: dataset_repo

    yield {"models": model_repo, "datasets": dataset_repo}
    app.dependency_overrides.clear()


def test_set_validation_dataset_happy_path(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    fakes["datasets"].datasets[("user-1", "dataset-1")] = _dataset_record()

    response = client.patch(
        "/models/model-1/validation",
        json={
            "datasetId": "dataset-1",
            "taskType": "image_cls",
            "preprocess": {"inputSize": 224, "mean": [0.5, 0.5, 0.5], "channelOrder": "rgb"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "model-1"
    assert body["validationFilename"] == "calib.npz"

    stored = fakes["models"].models[("user-1", "model-1")]
    assert stored.details["validationDatasetId"] == "dataset-1"
    assert stored.details["taskType"] == "image_cls"
    assert stored.details["preprocess"] == {
        "inputSize": 224,
        "mean": [0.5, 0.5, 0.5],
        "channelOrder": "rgb",
    }


def test_set_validation_dataset_defaults_preprocess_to_empty_dict(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    fakes["datasets"].datasets[("user-1", "dataset-1")] = _dataset_record()

    response = client.patch(
        "/models/model-1/validation",
        json={"datasetId": "dataset-1", "taskType": "lm"},
    )

    assert response.status_code == 200
    stored = fakes["models"].models[("user-1", "model-1")]
    assert stored.details["preprocess"] == {}


def test_set_validation_dataset_rejects_model_not_owned_by_caller(fakes: Any) -> None:
    fakes["datasets"].datasets[("user-1", "dataset-1")] = _dataset_record()

    response = client.patch(
        "/models/not-mine/validation",
        json={"datasetId": "dataset-1", "taskType": "image_cls"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_set_validation_dataset_rejects_missing_dataset(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()

    response = client.patch(
        "/models/model-1/validation",
        json={"datasetId": "does-not-exist", "taskType": "image_cls"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "dataset_not_found"


def test_set_validation_dataset_rejects_dataset_owned_by_someone_else(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    # Dataset belongs to a different user, so it's simply absent from user-1's view.
    fakes["datasets"].datasets[("user-2", "dataset-1")] = _dataset_record(user_id="user-2")

    response = client.patch(
        "/models/model-1/validation",
        json={"datasetId": "dataset-1", "taskType": "image_cls"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "dataset_not_found"


def test_set_validation_dataset_rejects_non_dataset_kind(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    fakes["datasets"].datasets[("user-1", "dataset-1")] = _dataset_record(kind="training")

    response = client.patch(
        "/models/model-1/validation",
        json={"datasetId": "dataset-1", "taskType": "image_cls"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_dataset_kind"


def test_set_validation_dataset_rejects_malformed_task_type(fakes: Any) -> None:
    fakes["models"].models[("user-1", "model-1")] = _model_record()
    fakes["datasets"].datasets[("user-1", "dataset-1")] = _dataset_record()

    response = client.patch(
        "/models/model-1/validation",
        json={"datasetId": "dataset-1", "taskType": "not_a_real_task"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
