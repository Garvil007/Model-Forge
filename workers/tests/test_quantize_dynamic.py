"""ops.quantize_dynamic: real INT8 dynamic quantization of a tiny model, one tool per
source format (ONNX Runtime, PyTorch TorchScript, TFLite via Keras)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnx.helper as helper
import pytest
import tensorflow as tf
import torch
import torch.nn as nn
from modelforge_catalog.methods import METHODS
from modelforge_catalog.models import ModelInfo
from modelforge_db.records import JobEventRecord, ModelRecord

from core.exceptions import JobCanceledError
from ops import quantize_dynamic

_MATRIX_SIZE = 64  # big enough that int8 weight savings outweigh QDQ-node overhead
_METHODS_BY_ID = {m.id: m for m in METHODS}


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


def _model_record(
    *, filename: str = "tiny.onnx", model_format: str = "onnx", size_bytes: int = 0,
    param_count: int | None = None,
) -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    return ModelRecord(
        user_id="user-1", model_id="model-1", filename=filename,
        s3_key=f"users/user-1/models/model-1{Path(filename).suffix}",
        size_bytes=size_bytes, format=model_format, family="generic", bits=32.0,
        param_count=param_count, details={}, status="ready", created_at=now, updated_at=now,
        ttl=0,
    )


def _assert_size_estimate_reasonable(model: ModelRecord, result: dict[str, Any]) -> None:
    spec = _METHODS_BY_ID["q_int8_dyn"]
    info = ModelInfo(
        format=model.format, family=model.family, bits=model.bits or 32.0,
        params=model.param_count or 0, size=model.size_bytes,
    )
    estimate = spec.size_estimate(info, {})
    assert estimate is not None
    # a hand-built tiny model is nowhere near the smooth-scaling regime the formula assumes
    # (fixed per-tensor/container overhead dominates), so this is a loose sanity band.
    assert estimate * 0.1 <= result["outputBytes"] <= estimate * 10


def _run_op(model: ModelRecord, model_bytes: bytes, control: Any = None) -> tuple[
    _FakeJobRepository, _FakeJobEventRepository, _FakeS3
]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(model)
    quantize_dynamic.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={}, operation=None,
        control=control or _AlwaysOkControl(), event_repo=events, job_repo=jobs,
        models_repo=models, s3_client=s3,
    )
    return jobs, events, s3


def _run(control: Any, s3: _FakeS3, jobs: _FakeJobRepository, events: _FakeJobEventRepository,
         models: _FakeModelRepository) -> None:
    quantize_dynamic.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={}, operation=None,
        control=control, event_repo=events, job_repo=jobs, models_repo=models, s3_client=s3,
    )


def test_run_succeeds_and_shrinks_model() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(
        size_bytes=len(model_bytes), param_count=_MATRIX_SIZE * _MATRIX_SIZE
    )
    s3 = _FakeS3({("mf-uploads", "users/user-1/models/model-1.onnx"): model_bytes})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(model)

    _run(_AlwaysOkControl(), s3, jobs, events, models)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["outputBytes"] < len(model_bytes)
    assert result["downloadName"] == "tiny.int8.onnx"
    assert result["measuredOnValidation"] is False
    assert float(result["metrics"]["Output similarity"]) > 0.9

    uploaded_bytes = s3.uploaded[("mf-results", result["s3Key"])]
    assert len(uploaded_bytes) == result["outputBytes"]
    reloaded = onnx.load_from_string(uploaded_bytes)
    onnx.checker.check_model(reloaded)

    stages = [event.stage for event in events.events]
    assert stages == ["Loading model", "Quantizing weights", "Measuring accuracy"]
    _assert_size_estimate_reasonable(model, result)


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


# ------------------------------------------------------------------------------ PyTorch


class _TinyLinear(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.lin1 = nn.Linear(_MATRIX_SIZE, _MATRIX_SIZE)
        self.lin2 = nn.Linear(_MATRIX_SIZE, _MATRIX_SIZE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.lin2(self.lin1(x))


def test_torchscript_quantizes_linear_layers(tmp_path: Path) -> None:
    module = torch.jit.trace(_TinyLinear(), torch.randn(1, _MATRIX_SIZE))
    path = tmp_path / "scripted.pt"
    torch.jit.save(module, str(path))
    model_bytes = path.read_bytes()
    model = _model_record(
        filename="tiny.pt", model_format="torchscript", size_bytes=len(model_bytes),
        param_count=2 * (_MATRIX_SIZE * _MATRIX_SIZE + _MATRIX_SIZE),
    )

    jobs, events, s3 = _run_op(model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert "not measured" in result["metrics"]["Output similarity"]

    out_path = tmp_path / "out.pt"
    out_path.write_bytes(s3.uploaded[("mf-results", result["s3Key"])])
    reloaded = torch.jit.load(str(out_path), map_location="cpu")
    assert "quantized::linear_dynamic" in str(reloaded.graph)
    _assert_size_estimate_reasonable(model, result)


def test_torch_statedict_is_refused_no_architecture_to_quantize(tmp_path: Path) -> None:
    state = {"lin.weight": torch.randn(_MATRIX_SIZE, _MATRIX_SIZE)}
    path = tmp_path / "state.pt"
    torch.save(state, str(path))
    model_bytes = path.read_bytes()
    model = _model_record(filename="tiny.pt", model_format="torch", size_bytes=len(model_bytes))

    jobs, _, _ = _run_op(model, model_bytes)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


# ---------------------------------------------------------------------------------- Keras


def test_keras_converts_to_tflite_with_dynamic_range_quantization(tmp_path: Path) -> None:
    keras_model = tf.keras.Sequential(
        [tf.keras.layers.Dense(_MATRIX_SIZE, input_shape=(_MATRIX_SIZE,))]
    )
    path = tmp_path / "tiny.h5"
    keras_model.save(str(path))
    model_bytes = path.read_bytes()
    model = _model_record(
        filename="tiny.h5", model_format="keras", size_bytes=len(model_bytes),
        param_count=_MATRIX_SIZE * _MATRIX_SIZE + _MATRIX_SIZE,
    )

    jobs, events, s3 = _run_op(model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["downloadName"] == "tiny.int8.tflite"
    assert float(result["metrics"]["Output similarity"]) > 0.9

    out_path = tmp_path / "out.tflite"
    out_bytes = s3.uploaded[("mf-results", result["s3Key"])]
    out_path.write_bytes(out_bytes)
    interpreter = tf.lite.Interpreter(model_path=str(out_path))
    interpreter.allocate_tensors()  # loads cleanly in its target runtime
    assert len(out_bytes) < len(model_bytes)
