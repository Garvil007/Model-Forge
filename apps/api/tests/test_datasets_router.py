"""GET /datasets — list only the caller's own datasets."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from modelforge_db.records import DatasetRecord, UserRecord

from app.auth import current_user
from app.main import app
from app.routers import datasets as datasets_router

client = TestClient(app)

_USER = UserRecord(
    user_id="user-1",
    email="user@example.com",
    plan="free",
    settings={},
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T00:00:00Z",
)


class _FakeDatasetRepository:
    def __init__(self) -> None:
        self.datasets: list[DatasetRecord] = []

    def list_for_user(self, user_id: str, *, limit: int = 50) -> list[DatasetRecord]:
        return [record for record in self.datasets if record.user_id == user_id][:limit]


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
    repo = _FakeDatasetRepository()
    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[datasets_router.get_dataset_repository] = lambda: repo
    yield {"datasets": repo}
    app.dependency_overrides.clear()


def test_list_datasets_returns_only_callers_own_datasets(fakes: Any) -> None:
    fakes["datasets"].datasets.append(_dataset_record())
    fakes["datasets"].datasets.append(
        _dataset_record(user_id="user-2", dataset_id="dataset-2", filename="other.npz")
    )

    response = client.get("/datasets")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": "dataset-1",
            "filename": "calib.npz",
            "size": 1_000,
            "kind": "dataset",
            "createdAt": "2026-01-01T00:00:00Z",
        }
    ]


def test_list_datasets_empty_when_none_uploaded(fakes: Any) -> None:
    response = client.get("/datasets")

    assert response.status_code == 200
    assert response.json() == []
