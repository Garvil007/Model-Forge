"""ops.quantize_dynamic: real onnxruntime dynamic int8 quantization of a tiny model."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import numpy as np
import onnx
import onnx.helper as helper
import pytest
from modelforge_db.records import JobEventRecord, ModelRecord

from core.exceptions import JobCanceledError
from ops import quantize_dynamic

_MATRIX_SIZE = 64  # big enough that int8 weight savings outweigh QDQ-node overhead


def _tiny_onnx_bytes() -> bytes:
    rng = np.random.default_rng(0)
    x = helper.make_tensor_value_info("X", onnx.TensorProto.FLOAT, [1, _MATRIX_SIZE])
    y = helper.make_tensor_value_info("Y", onnx.TensorProto.FLOAT, [1, _MATRIX_SIZE])
    weight = helper.make_tensor(
        "W",
        onnx.TensorProto.FLOAT,
        [_MATRIX_SIZE, _MATRIX_SIZE],
        rng.standard_normal([_MATRIX_SIZE, _MATRIX_SIZE]).astype(np.float32).flatten().tolist(),
    )
    node = helper.make_node("MatMul", ["X", "W"], ["Y"])
    graph = helper.make_graph([node], "g", [x], [y], initializer=[weight])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


class _FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects
        self.uploaded: dict[tuple[str, str], bytes] = {}

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        with open(local_path, "wb") as fh:
            fh.write(self.objects[(bucket, key)])

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        with open(local_path, "rb") as fh:
            self.uploaded[(bucket, key)] = fh.read()


class _FakeModelRepository:
    def __init__(self, record: ModelRecord) -> None:
        self.record = record

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        return self.record


class _FakeJobRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_progress(self, user_id: str, job_id: str, *, status: str, progress_percent: int,
                         result: dict[str, Any] | None = None, error: dict[str, Any] | None = None,
                         timings: dict[str, Any] | None = None) -> None:
        self.calls.append({"status": status, "progress_percent": progress_percent,
                            "result": result, "error": error})


class _FakeJobEventRepository:
    def __init__(self) -> None:
        self.events: list[JobEventRecord] = []

    def append(self, user_id: str, job_id: str, *, stage: str, message: str,
               percent: int | None = None) -> JobEventRecord:
        event = JobEventRecord(user_id=user_id, job_id=job_id, stage=stage, message=message,
                                percent=percent, timestamp_ms=0, ttl=0)
        self.events.append(event)
        return event


class _AlwaysOkControl:
    def check(self) -> None:
        pass


class _CancelAfterNControl:
    def __init__(self, n: int) -> None:
        self.n = n
        self.calls = 0

    def check(self) -> None:
        self.calls += 1
        if self.calls > self.n:
            raise JobCanceledError("canceled")


def _model_record() -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    return ModelRecord(
        user_id="user-1", model_id="model-1", filename="tiny.onnx",
        s3_key="users/user-1/models/model-1.onnx",
        size_bytes=0, format="onnx", family="generic", bits=32.0, param_count=None, details={},
        status="ready", created_at=now, updated_at=now, ttl=0,
    )


def _run(control: Any, s3: _FakeS3, jobs: _FakeJobRepository, events: _FakeJobEventRepository,
         models: _FakeModelRepository) -> None:
    quantize_dynamic.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={}, operation=None,
        control=control, event_repo=events, job_repo=jobs, models_repo=models, s3_client=s3,
    )


def test_run_succeeds_and_shrinks_model() -> None:
    model_bytes = _tiny_onnx_bytes()
    s3 = _FakeS3({("mf-uploads", "users/user-1/models/model-1.onnx"): model_bytes})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(_model_record())

    _run(_AlwaysOkControl(), s3, jobs, events, models)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["outputBytes"] < len(model_bytes)
    assert result["downloadName"] == "tiny.int8.onnx"
    assert result["measuredOnValidation"] is False

    uploaded_bytes = s3.uploaded[("mf-results", result["s3Key"])]
    assert len(uploaded_bytes) == result["outputBytes"]
    reloaded = onnx.load_from_string(uploaded_bytes)
    onnx.checker.check_model(reloaded)

    stages = [event.stage for event in events.events]
    assert stages == ["Loading model", "Quantizing weights", "Measuring accuracy"]


def test_cancel_between_stages_propagates_without_terminal_update() -> None:
    model_bytes = _tiny_onnx_bytes()
    s3 = _FakeS3({("mf-uploads", "users/user-1/models/model-1.onnx"): model_bytes})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(_model_record())

    with pytest.raises(JobCanceledError):
        _run(_CancelAfterNControl(0), s3, jobs, events, models)

    assert jobs.calls == []  # op never wrote a terminal status itself


def test_corrupt_model_fails_cleanly_not_a_crash() -> None:
    s3 = _FakeS3({("mf-uploads", "users/user-1/models/model-1.onnx"): b"not an onnx file"})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(_model_record())

    _run(_AlwaysOkControl(), s3, jobs, events, models)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] in ("unknown", "unsupported_operator")


def test_cleans_up_local_files() -> None:
    model_bytes = _tiny_onnx_bytes()
    s3 = _FakeS3({("mf-uploads", "users/user-1/models/model-1.onnx"): model_bytes})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(_model_record())

    tmp_before = set(os.listdir(os.environ.get("TEMP", "/tmp")))
    _run(_AlwaysOkControl(), s3, jobs, events, models)
    tmp_after = set(os.listdir(os.environ.get("TEMP", "/tmp")))
    leftover = {name for name in (tmp_after - tmp_before) if name.startswith("mf-quantize-")}
    assert leftover == set()
