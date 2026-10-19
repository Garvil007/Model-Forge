"""core.evaluation: evaluate_or_fallback's task-type dispatch, no-validation-data fallback,
and graceful degradation when a validation dataset is configured but unusable."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import numpy as np
import pytest
from modelforge_db.records import DatasetRecord, ModelRecord
from PIL import Image

from core import evaluation


def _model_record(details: dict[str, Any] | None = None) -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    return ModelRecord(
        user_id="user-1", model_id="model-1", filename="model.onnx",
        s3_key="users/user-1/models/model-1.onnx", size_bytes=10, format="onnx",
        family="generic", bits=32.0, param_count=10, details=details or {}, status="ready",
        created_at=now, updated_at=now, ttl=0,
    )


class _FakeDatasetsRepo:
    def __init__(self, record: DatasetRecord) -> None:
        self._record = record

    def get(self, user_id: str, dataset_id: str) -> DatasetRecord:
        return self._record


class _FakeS3:
    def __init__(
        self, payload: bytes | None = None, *, raise_error: Exception | None = None
    ) -> None:
        self._payload = payload
        self._raise_error = raise_error

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        if self._raise_error is not None:
            raise self._raise_error
        with open(local_path, "wb") as handle:
            handle.write(self._payload or b"")


class _AlwaysOkControl:
    def check(self) -> None:
        pass


def _dataset_record(filename: str) -> DatasetRecord:
    now = datetime.now(UTC).isoformat()
    return DatasetRecord(
        user_id="user-1", dataset_id="dataset-1", kind="validation", filename=filename,
        s3_key="users/user-1/datasets/dataset-1", size_bytes=10, model_id="model-1",
        created_at=now, ttl=0,
    )


class _ConstantLogitsRunner:
    """Always predicts class 0 (or token id 0), regardless of input."""

    def __init__(self, vocab_size: int = 4) -> None:
        self._vocab_size = vocab_size

    def predict(self, batch: np.ndarray) -> np.ndarray:
        logits = np.zeros(self._vocab_size, dtype=np.float32)
        logits[0] = 10.0
        return logits


# --------------------------------------------------------------------- no validation data


def test_falls_back_to_caller_supplied_fallback_when_no_validation_dataset() -> None:
    model = _model_record(details={})
    runner_factory_called = False

    def _runner_factory() -> tuple[Any, Any]:
        nonlocal runner_factory_called
        runner_factory_called = True
        return _ConstantLogitsRunner(), _ConstantLogitsRunner()

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "0.9999"},
        runner_factory=_runner_factory,
    )

    assert metrics == {"Output similarity": "0.9999"}
    assert measured is False
    assert detail is None
    assert runner_factory_called is False


def test_falls_back_when_runner_factory_is_none_even_with_validation_dataset_configured() -> None:
    model = _model_record(
        details={"validationDatasetId": "dataset-1", "taskType": "image_cls"}
    )

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "0.5"},
        runner_factory=None,
    )

    assert metrics == {"Output similarity": "0.5"}
    assert measured is False
    assert detail is None


# ----------------------------------------------------------------- graceful degradation


def test_degrades_to_fallback_with_note_when_dataset_download_fails() -> None:
    model = _model_record(
        details={"validationDatasetId": "dataset-1", "taskType": "image_cls"}
    )
    datasets_repo = _FakeDatasetsRepo(_dataset_record("val.zip"))
    s3 = _FakeS3(raise_error=RuntimeError("s3 unavailable"))

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "0.75"},
        runner_factory=lambda: (_ConstantLogitsRunner(), _ConstantLogitsRunner()),
        s3=s3,
        datasets_repo=datasets_repo,
        validation_bucket="mf-datasets",
    )

    assert measured is False
    assert detail is None
    assert metrics["Output similarity"] == "0.75"
    assert "s3 unavailable" in metrics["note"]


def test_degrades_to_fallback_when_task_type_has_no_dispatch() -> None:
    model = _model_record(
        details={"validationDatasetId": "dataset-1", "taskType": "not_a_real_task_type"}
    )
    datasets_repo = _FakeDatasetsRepo(_dataset_record("val.zip"))
    s3 = _FakeS3(payload=b"irrelevant")

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "0.1"},
        runner_factory=lambda: (_ConstantLogitsRunner(), _ConstantLogitsRunner()),
        s3=s3,
        datasets_repo=datasets_repo,
        validation_bucket="mf-datasets",
    )

    assert measured is False
    assert "note" in metrics


# --------------------------------------------------------------------------- image_cls


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _imagefolder_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("cat/1.png", _png_bytes((255, 0, 0)))
        archive.writestr("cat/2.png", _png_bytes((255, 0, 0)))
        archive.writestr("dog/1.png", _png_bytes((0, 255, 0)))
    return buffer.getvalue()


def test_dispatches_image_cls_to_topk_evaluator() -> None:
    model = _model_record(
        details={"validationDatasetId": "dataset-1", "taskType": "image_cls", "preprocess": {}}
    )
    datasets_repo = _FakeDatasetsRepo(_dataset_record("val.zip"))
    s3 = _FakeS3(payload=_imagefolder_zip_bytes())

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "not used"},
        runner_factory=lambda: (_ConstantLogitsRunner(2), _ConstantLogitsRunner(2)),
        s3=s3,
        datasets_repo=datasets_repo,
        validation_bucket="mf-datasets",
    )

    assert measured is True
    assert detail["taskType"] == "image_cls"
    assert detail["metricName"] == "Top-1 accuracy"
    # both runners always predict class 0 ("cat"), which is 2/3 of the samples.
    assert detail["before"] == pytest.approx(2 / 3)
    assert detail["after"] == pytest.approx(2 / 3)
    assert "Top-1 accuracy" in metrics


# ----------------------------------------------------------------------------- detection


def _detection_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("images/1.jpg", _png_bytes((10, 10, 10)))
        archive.writestr("labels/1.txt", "0 0.5 0.5 0.2 0.2\n")
    return buffer.getvalue()


class _NoDetectionsRunner:
    def predict(self, image: np.ndarray) -> list[Any]:
        return []


def test_dispatches_detection_to_map_evaluator() -> None:
    model = _model_record(
        details={"validationDatasetId": "dataset-1", "taskType": "detection", "preprocess": {}}
    )
    datasets_repo = _FakeDatasetsRepo(_dataset_record("val.zip"))
    s3 = _FakeS3(payload=_detection_zip_bytes())

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "not used"},
        runner_factory=lambda: (_NoDetectionsRunner(), _NoDetectionsRunner()),
        s3=s3,
        datasets_repo=datasets_repo,
        validation_bucket="mf-datasets",
    )

    assert measured is True
    assert detail["taskType"] == "detection"
    assert detail["metricName"] == "mAP50-95"
    # no predictions at all -> 0 mAP for both runners.
    assert detail["before"] == 0.0
    assert detail["after"] == 0.0


# ------------------------------------------------------------------------------ text_cls


class _FakeTokenizer:
    def encode(self, text: str) -> list[int]:
        return [len(text) % 7, 1, 2]


def test_dispatches_text_cls_to_classification_evaluator(monkeypatch) -> None:
    model = _model_record(
        details={
            "validationDatasetId": "dataset-1", "taskType": "text_cls", "repoId": "fake/repo",
        }
    )
    monkeypatch.setattr(evaluation, "_build_tokenizer", lambda _model: _FakeTokenizer())
    datasets_repo = _FakeDatasetsRepo(_dataset_record("val.jsonl"))
    rows = [{"text": "good", "label": 0}, {"text": "bad", "label": 1}]
    payload = ("\n".join(json.dumps(row) for row in rows)).encode("utf-8")
    s3 = _FakeS3(payload=payload)

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "not used"},
        runner_factory=lambda: (_ConstantLogitsRunner(2), _ConstantLogitsRunner(2)),
        s3=s3,
        datasets_repo=datasets_repo,
        validation_bucket="mf-datasets",
    )

    assert measured is True
    assert detail["taskType"] == "text_cls"
    assert detail["metricName"] == "Accuracy"
    # the runner always predicts class 0; half the rows are labeled 0.
    assert detail["before"] == pytest.approx(0.5)


# ------------------------------------------------------------------------------------ lm


def test_dispatches_lm_to_perplexity_evaluator(monkeypatch) -> None:
    model = _model_record(
        details={"validationDatasetId": "dataset-1", "taskType": "lm", "repoId": "fake/repo"}
    )
    monkeypatch.setattr(evaluation, "_build_tokenizer", lambda _model: _FakeTokenizer())
    datasets_repo = _FakeDatasetsRepo(_dataset_record("val.txt"))
    s3 = _FakeS3(payload=b"hello world this is a tiny language modeling validation chunk")

    class _LmRunner:
        def predict(self, batch: np.ndarray) -> np.ndarray:
            seq_len = batch.shape[1]
            logits = np.zeros((1, seq_len, 8), dtype=np.float32)
            logits[:, :, 0] = 10.0
            return logits

    metrics, measured, detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=_AlwaysOkControl(),
        fallback=lambda: {"Output similarity": "not used"},
        runner_factory=lambda: (_LmRunner(), _LmRunner()),
        s3=s3,
        datasets_repo=datasets_repo,
        validation_bucket="mf-datasets",
    )

    assert measured is True
    assert detail["taskType"] == "lm"
    assert detail["metricName"] == "Perplexity"
    assert detail["before"] > 0


# --------------------------------------------------------------------- build_preprocess_spec


def test_build_preprocess_spec_converts_mean_std_lists_to_tuples() -> None:
    spec = evaluation.build_preprocess_spec(
        {"preprocess": {"input_size": 32, "mean": [0.1, 0.2, 0.3], "std": [0.1, 0.1, 0.1]}}
    )

    assert spec.input_size == 32
    assert spec.mean == (0.1, 0.2, 0.3)
    assert isinstance(spec.std, tuple)


def test_build_preprocess_spec_defaults_when_no_preprocess_key() -> None:
    spec = evaluation.build_preprocess_spec({})

    assert spec.input_size == 224


def test_build_tokenizer_raises_evaluation_error_without_repo_id() -> None:
    model = _model_record(details={})

    with pytest.raises(evaluation.EvaluationError):
        evaluation._build_tokenizer(model)
