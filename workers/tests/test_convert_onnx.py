"""ops.convert_onnx: TorchScript/Keras/YOLO/safetensors(HF) -> ONNX, using tiny real models
built inside the test and reloaded for real in `onnxruntime`."""

from __future__ import annotations

import io

import pytest
import tensorflow as tf
import torch
import torch.nn as nn
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_onnx

_OPS_BY_ID = {op.id: op for op in CONVERTS}
_C_ONNX = _OPS_BY_ID["c_onnx"]


def _tiny_torchscript_bytes() -> bytes:
    module = nn.Sequential(nn.Linear(4, 3), nn.ReLU())
    scripted = torch.jit.trace(module, (torch.randn(1, 4),))
    buffer = io.BytesIO()
    torch.jit.save(scripted, buffer)
    return buffer.getvalue()


def test_torchscript_source_exports_to_onnx_and_matches_output() -> None:
    model = model_record(filename="model.pt", model_format="torchscript")
    jobs, events, s3 = run_convert(
        convert_onnx, _C_ONNX, model, _tiny_torchscript_bytes(),
        params={"opset": "17", "shape": "1,4", "dynamic": True},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99
    stages = {e.stage for e in events.events}
    assert stages == {"Loading model", "Converting to ONNX", "Checking outputs match"}


def _tiny_keras_bytes() -> bytes:
    import tempfile
    from pathlib import Path

    tf.keras.utils.set_random_seed(0)
    model = tf.keras.Sequential(
        [tf.keras.layers.Input(shape=(4,)), tf.keras.layers.Dense(3, activation="relu")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.h5"
        model.save(str(path))
        return path.read_bytes()


def test_keras_source_exports_to_onnx_via_savedmodel_and_tf2onnx_cli() -> None:
    model = model_record(filename="model.h5", model_format="keras")
    jobs, _events, _s3 = run_convert(
        convert_onnx, _C_ONNX, model, _tiny_keras_bytes(), params={"opset": "17"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99


def test_torch_statedict_source_is_refused_cleanly() -> None:
    model = model_record(filename="model.pt", model_format="torch")
    state = {"w": torch.randn(3, 4)}
    buffer = io.BytesIO()
    torch.save(state, buffer)
    jobs, _events, _s3 = run_convert(convert_onnx, _C_ONNX, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_safetensors_without_hf_repo_id_is_refused_cleanly() -> None:
    import safetensors.torch

    model = model_record(filename="model.safetensors", model_format="safetensors", details={})
    buffer = safetensors.torch.save({"w": torch.randn(2, 2)})
    jobs, _events, _s3 = run_convert(convert_onnx, _C_ONNX, model, buffer)
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_yolo_source_exports_to_onnx() -> None:
    pytest.importorskip("ultralytics")
    import tempfile
    from pathlib import Path

    from ultralytics import YOLO

    with tempfile.TemporaryDirectory() as tmp:
        checkpoint = Path(tmp) / "tiny.pt"
        yolo = YOLO("yolo11n.yaml")
        yolo.save(str(checkpoint))
        model_bytes = checkpoint.read_bytes()

    model = model_record(filename="model.pt", model_format="yolo")
    jobs, _events, _s3 = run_convert(
        convert_onnx, _C_ONNX, model, model_bytes, params={"opset": "17", "dynamic": False},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
