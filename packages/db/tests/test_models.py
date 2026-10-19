from __future__ import annotations

from typing import Any

from modelforge_db import ModelRepository, NotFoundError

from .conftest import unique_id


def test_create_and_get(table: Any) -> None:
    repo = ModelRepository(table)
    user_id = unique_id()

    created = repo.create(
        user_id,
        filename="resnet50.onnx",
        s3_key=f"uploads/{user_id}/resnet50.onnx",
        size_bytes=102_400_000,
        format="onnx",
        family="resnet",
        bits=32,
        param_count=25_000_000,
        details={"accuracy": 0.761},
    )

    fetched = repo.get(user_id, created.model_id)

    assert fetched == created
    assert fetched.details == {"accuracy": 0.761}
    assert fetched.ttl > 0


def test_get_missing_model_raises_not_found(table: Any) -> None:
    repo = ModelRepository(table)

    try:
        repo.get(unique_id(), unique_id())
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")


def test_list_for_user_returns_newest_first(table: Any) -> None:
    repo = ModelRepository(table)
    user_id = unique_id()

    first = repo.create(
        user_id, filename="a.onnx", s3_key="a", size_bytes=1, format="onnx", family="x"
    )
    second = repo.create(
        user_id, filename="b.onnx", s3_key="b", size_bytes=1, format="onnx", family="x"
    )

    listed = repo.list_for_user(user_id)

    assert [model.model_id for model in listed] == [second.model_id, first.model_id]


def test_update_status(table: Any) -> None:
    repo = ModelRepository(table)
    user_id = unique_id()
    created = repo.create(
        user_id, filename="a.onnx", s3_key="a", size_bytes=1, format="onnx", family="x"
    )

    updated = repo.update_status(user_id, created.model_id, "archived")

    assert updated.status == "archived"
    assert repo.get(user_id, created.model_id).status == "archived"


def test_update_validation_merges_details_without_touching_other_keys(table: Any) -> None:
    repo = ModelRepository(table)
    user_id = unique_id()
    created = repo.create(
        user_id,
        filename="a.onnx",
        s3_key="a",
        size_bytes=1,
        format="onnx",
        family="x",
        details={"source": "upload"},
    )

    updated = repo.update_validation(
        user_id,
        created.model_id,
        validation_dataset_id="dataset-1",
        validation_filename="val.npz",
        task_type="image_cls",
        preprocess={"inputSize": 224, "mean": [0.5, 0.5, 0.5]},
    )

    assert updated.details["source"] == "upload"
    assert updated.details["validationDatasetId"] == "dataset-1"
    assert updated.details["validationFilename"] == "val.npz"
    assert updated.details["taskType"] == "image_cls"
    assert updated.details["preprocess"] == {"inputSize": 224, "mean": [0.5, 0.5, 0.5]}
    assert repo.get(user_id, created.model_id).details == updated.details


def test_update_validation_missing_model_raises_not_found(table: Any) -> None:
    repo = ModelRepository(table)

    try:
        repo.update_validation(
            unique_id(),
            unique_id(),
            validation_dataset_id="dataset-1",
            validation_filename="val.npz",
            task_type="image_cls",
            preprocess={},
        )
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")


def test_delete_removes_model(table: Any) -> None:
    repo = ModelRepository(table)
    user_id = unique_id()
    created = repo.create(
        user_id, filename="a.onnx", s3_key="a", size_bytes=1, format="onnx", family="x"
    )

    repo.delete(user_id, created.model_id)

    try:
        repo.get(user_id, created.model_id)
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")
