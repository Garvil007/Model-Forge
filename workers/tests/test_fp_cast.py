"""ops.fp_cast: FP16/BF16 weight casting across ONNX, PyTorch (state_dict + TorchScript),
Keras and safetensors, using tiny models generated inside the test. Also checks each real
output size against the catalog's `q_fp16`/`q_bf16` size-estimate formula.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import onnx
import onnx.helper as helper
import pytest
import safetensors.torch
import tensorflow as tf
import torch
import torch.nn as nn
from modelforge_catalog.methods import METHODS
from modelforge_catalog.models import ModelInfo
from modelforge_db.records import JobEventRecord, ModelRecord

from core.exceptions import JobCanceledError
from ops import fp_cast

_METHODS_BY_ID = {m.id: m for m in METHODS}
_SIZE = 32


# --------------------------------------------------------------------------------- fakes


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

    def update_progress(
        self, user_id: str, job_id: str, *, status: str, progress_percent: int,
        result: dict[str, Any] | None = None, error: dict[str, Any] | None = None,
        timings: dict[str, Any] | None = None,
    ) -> None:
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


class _FakeOperation:
    def __init__(self, op_id: str) -> None:
        self.id = op_id


def _model_record(*, filename: str, model_format: str, bits: float = 32.0,
                   size_bytes: int = 0, param_count: int | None = None) -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    return ModelRecord(
        user_id="user-1", model_id="model-1", filename=filename,
        s3_key=f"users/user-1/models/model-1{Path(filename).suffix}",
        size_bytes=size_bytes, format=model_format, family="other", bits=bits,
        param_count=param_count, details={}, status="ready", created_at=now, updated_at=now,
        ttl=0,
    )


def _run(operation_id: str, model: ModelRecord, model_bytes: bytes,
          control: Any = None) -> tuple[_FakeJobRepository, _FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(model)
    fp_cast.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={},
        operation=_FakeOperation(operation_id), control=control or _AlwaysOkControl(),
        event_repo=events, job_repo=jobs, models_repo=models, s3_client=s3,
    )
    return jobs, events, s3


def _assert_size_estimate_reasonable(
    operation_id: str, model: ModelRecord, result: dict[str, Any]
) -> None:
    spec = _METHODS_BY_ID[operation_id]
    info = ModelInfo(
        format=model.format, family=model.family, bits=model.bits or 32.0,
        params=model.param_count or 0, size=model.size_bytes,
    )
    estimate = spec.size_estimate(info, {})
    assert estimate is not None
    # a hand-built tiny model is nowhere near the smooth-scaling regime the formula assumes
    # (fixed per-tensor/container overhead dominates), so this is a loose sanity band, not a
    # tight assertion — real models are what the formula is tuned against.
    assert estimate * 0.1 <= result["outputBytes"] <= estimate * 10


# --------------------------------------------------------------------------------- ONNX


def _tiny_onnx_bytes() -> bytes:
    rng = np.random.default_rng(0)
    x = helper.make_tensor_value_info("X", onnx.TensorProto.FLOAT, [1, _SIZE])
    y = helper.make_tensor_value_info("Y", onnx.TensorProto.FLOAT, [1, _SIZE])
    weight = helper.make_tensor(
        "W", onnx.TensorProto.FLOAT, [_SIZE, _SIZE],
        rng.standard_normal([_SIZE, _SIZE]).astype(np.float32).flatten().tolist(),
    )
    node = helper.make_node("MatMul", ["X", "W"], ["Y"])
    graph = helper.make_graph([node], "g", [x], [y], initializer=[weight])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


def test_onnx_fp16_casts_and_measures_real_similarity() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(
        filename="tiny.onnx", model_format="onnx", size_bytes=len(model_bytes),
        param_count=_SIZE * _SIZE,
    )
    jobs, events, s3 = _run("q_fp16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["downloadName"] == "tiny.fp16.onnx"
    assert float(result["metrics"]["Output similarity"]) > 0.99
    reloaded = onnx.load_from_string(s3.uploaded[("mf-results", result["s3Key"])])
    onnx.checker.check_model(reloaded)
    _assert_size_estimate_reasonable("q_fp16", model, result)


def test_onnx_bf16_is_unsupported() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(filename="tiny.onnx", model_format="onnx", size_bytes=len(model_bytes))
    jobs, _, _ = _run("q_bf16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_fp16_refuses_an_already_16bit_model() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(
        filename="tiny.onnx", model_format="onnx", bits=16.0, size_bytes=len(model_bytes),
    )
    jobs, _, _ = _run("q_fp16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"
    assert "16-bit" in jobs.calls[-1]["error"]["message"]


# ------------------------------------------------------------------------------ PyTorch


def _tiny_torch_statedict_bytes(tmp_path: Path) -> bytes:
    state = {"layer.weight": torch.randn(_SIZE, _SIZE), "layer.bias": torch.randn(_SIZE)}
    path = tmp_path / "state.pt"
    torch.save(state, str(path))
    return path.read_bytes()


def test_torch_statedict_fp16_casts_every_float_tensor(tmp_path: Path) -> None:
    model_bytes = _tiny_torch_statedict_bytes(tmp_path)
    model = _model_record(
        filename="tiny.pt", model_format="torch", size_bytes=len(model_bytes),
        param_count=_SIZE * _SIZE + _SIZE,
    )
    jobs, _, s3 = _run("q_fp16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert "not measured" in result["metrics"]["Output similarity"]

    out_path = tmp_path / "out.pt"
    out_path.write_bytes(s3.uploaded[("mf-results", result["s3Key"])])
    reloaded = torch.load(str(out_path), map_location="cpu", weights_only=True)
    assert reloaded["layer.weight"].dtype == torch.float16
    assert reloaded["layer.bias"].dtype == torch.float16
    _assert_size_estimate_reasonable("q_fp16", model, result)


def test_torch_statedict_bf16_casts_every_float_tensor(tmp_path: Path) -> None:
    model_bytes = _tiny_torch_statedict_bytes(tmp_path)
    model = _model_record(
        filename="tiny.pt", model_format="torch", size_bytes=len(model_bytes),
        param_count=_SIZE * _SIZE + _SIZE,
    )
    jobs, _, s3 = _run("q_bf16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    out_path = tmp_path / "out.pt"
    out_path.write_bytes(s3.uploaded[("mf-results", result["s3Key"])])
    reloaded = torch.load(str(out_path), map_location="cpu", weights_only=True)
    assert reloaded["layer.weight"].dtype == torch.bfloat16


class _TinyLinear(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.lin = nn.Linear(_SIZE, _SIZE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.lin(x)


def _tiny_torchscript_bytes(tmp_path: Path) -> bytes:
    module = torch.jit.trace(_TinyLinear(), torch.randn(1, _SIZE))
    path = tmp_path / "scripted.pt"
    torch.jit.save(module, str(path))
    return path.read_bytes()


def test_torchscript_fp16_halves_the_module(tmp_path: Path) -> None:
    model_bytes = _tiny_torchscript_bytes(tmp_path)
    model = _model_record(
        filename="tiny.pt", model_format="torchscript", size_bytes=len(model_bytes),
        param_count=_SIZE * _SIZE + _SIZE,
    )
    jobs, _, s3 = _run("q_fp16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    out_path = tmp_path / "out.pt"
    out_path.write_bytes(s3.uploaded[("mf-results", result["s3Key"])])
    reloaded = torch.jit.load(str(out_path), map_location="cpu")
    assert next(reloaded.parameters()).dtype == torch.float16
    _assert_size_estimate_reasonable("q_fp16", model, result)


def test_torchscript_bf16_is_unsupported(tmp_path: Path) -> None:
    model_bytes = _tiny_torchscript_bytes(tmp_path)
    model = _model_record(
        filename="tiny.pt", model_format="torchscript", size_bytes=len(model_bytes),
    )
    jobs, _, _ = _run("q_bf16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


# --------------------------------------------------------------------------- safetensors


def _tiny_safetensors_bytes(tmp_path: Path) -> bytes:
    tensors = {"weight": torch.randn(_SIZE, _SIZE), "bias": torch.randn(_SIZE)}
    path = tmp_path / "tiny.safetensors"
    safetensors.torch.save_file(tensors, str(path))
    return path.read_bytes()


@pytest.mark.parametrize("operation_id", ["q_fp16", "q_bf16"])
def test_safetensors_casts_every_tensor(tmp_path: Path, operation_id: str) -> None:
    model_bytes = _tiny_safetensors_bytes(tmp_path)
    model = _model_record(
        filename="tiny.safetensors", model_format="safetensors", size_bytes=len(model_bytes),
        param_count=_SIZE * _SIZE + _SIZE,
    )
    jobs, _, s3 = _run(operation_id, model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    out_path = tmp_path / "out.safetensors"
    out_path.write_bytes(s3.uploaded[("mf-results", result["s3Key"])])
    reloaded = safetensors.torch.load_file(str(out_path))
    expected = torch.float16 if operation_id == "q_fp16" else torch.bfloat16
    assert reloaded["weight"].dtype == expected
    assert reloaded["bias"].dtype == expected
    _assert_size_estimate_reasonable(operation_id, model, result)


# -------------------------------------------------------------------------------- Keras


def _tiny_keras_h5_bytes(tmp_path: Path) -> bytes:
    model = tf.keras.Sequential([tf.keras.layers.Dense(_SIZE, input_shape=(_SIZE,))])
    path = tmp_path / "tiny.h5"
    model.save(str(path))
    return path.read_bytes()


def test_keras_fp16_halves_hdf5_float_datasets_and_measures_similarity(tmp_path: Path) -> None:
    model_bytes = _tiny_keras_h5_bytes(tmp_path)
    model = _model_record(
        filename="tiny.h5", model_format="keras", size_bytes=len(model_bytes),
        param_count=_SIZE * _SIZE + _SIZE,
    )
    jobs, _, s3 = _run("q_fp16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert float(result["metrics"]["Output similarity"]) > 0.95

    out_path = tmp_path / "out.h5"
    out_path.write_bytes(s3.uploaded[("mf-results", result["s3Key"])])
    with h5py.File(out_path, "r") as handle:
        float_dtypes = set()
        handle.visititems(
            lambda name, obj: float_dtypes.add(obj.dtype)
            if isinstance(obj, h5py.Dataset) and obj.dtype.kind == "f"
            else None
        )
    assert all(dtype.itemsize == 2 for dtype in float_dtypes)
    _assert_size_estimate_reasonable("q_fp16", model, result)


def test_keras_bf16_is_unsupported(tmp_path: Path) -> None:
    model_bytes = _tiny_keras_h5_bytes(tmp_path)
    model = _model_record(filename="tiny.h5", model_format="keras", size_bytes=len(model_bytes))
    jobs, _, _ = _run("q_bf16", model, model_bytes)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


# ---------------------------------------------------------------------------- lifecycle


def test_cancel_between_stages_propagates_without_terminal_update() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(filename="tiny.onnx", model_format="onnx", size_bytes=len(model_bytes))

    with pytest.raises(JobCanceledError):
        _run("q_fp16", model, model_bytes, control=_CancelAfterNControl(0))


def test_corrupt_model_fails_cleanly_not_a_crash() -> None:
    model = _model_record(filename="tiny.onnx", model_format="onnx")
    jobs, _, _ = _run("q_fp16", model, b"not an onnx file")

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] in ("unknown", "unsupported_operator")


def test_cleans_up_local_files() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(filename="tiny.onnx", model_format="onnx", size_bytes=len(model_bytes))

    tmp_before = set(os.listdir(os.environ.get("TEMP", "/tmp")))
    _run("q_fp16", model, model_bytes)
    tmp_after = set(os.listdir(os.environ.get("TEMP", "/tmp")))
    leftover = {name for name in (tmp_after - tmp_before) if name.startswith("mf-fpcast-")}
    assert leftover == set()
