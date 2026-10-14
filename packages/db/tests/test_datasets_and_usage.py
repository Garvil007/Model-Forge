from __future__ import annotations

from typing import Any

from modelforge_db import DatasetRepository, UsageRepository

from .conftest import unique_id


def test_dataset_create_get_list(table: Any) -> None:
    repo = DatasetRepository(table)
    user_id = unique_id()

    first = repo.create(user_id, kind="calibration", filename="a.npz", s3_key="a", size_bytes=1)
    second = repo.create(user_id, kind="validation", filename="b.npz", s3_key="b", size_bytes=1)

    assert repo.get(user_id, first.dataset_id) == first
    listed = repo.list_for_user(user_id)
    assert [dataset.dataset_id for dataset in listed] == [second.dataset_id, first.dataset_id]


def test_dataset_delete(table: Any) -> None:
    repo = DatasetRepository(table)
    user_id = unique_id()
    created = repo.create(user_id, kind="training", filename="a.npz", s3_key="a", size_bytes=1)

    repo.delete(user_id, created.dataset_id)

    assert repo.list_for_user(user_id) == []


def test_usage_get_defaults_to_zero_when_absent(table: Any) -> None:
    repo = UsageRepository(table)
    user_id = unique_id()

    usage = repo.get(user_id, "2026-10")

    assert usage.jobs_run == 0
    assert usage.cpu_seconds == 0
    assert usage.gpu_seconds == 0


def test_usage_increment_is_additive(table: Any) -> None:
    repo = UsageRepository(table)
    user_id = unique_id()

    repo.increment(user_id, "2026-10", jobs_run=1, cpu_seconds=30)
    updated = repo.increment(user_id, "2026-10", jobs_run=1, cpu_seconds=15, gpu_seconds=5)

    assert updated.jobs_run == 2
    assert updated.cpu_seconds == 45
    assert updated.gpu_seconds == 5
    assert repo.get(user_id, "2026-10") == updated
