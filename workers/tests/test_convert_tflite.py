"""ops.convert_tflite: Keras/ONNX/YOLO -> TFLite, using tiny real models built inside the
test and reloaded for real via `tf.lite.Interpreter`."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import onnx
import onnx.helper as helper
import pytest
import tensorflow as tf
import torch
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_tflite

_C_TFLITE = {op.id: op for op in CONVERTS}["c_tflite"]


def _tiny_keras_bytes() -> bytes:
    tf.keras.utils.set_random_seed(0)
    model = tf.keras.Sequential(
        [tf.keras.layers.Input(shape=(4,)), tf.keras.layers.Dense(3, activation="relu")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.h5"
        model.save(str(path))
        return path.read_bytes()


def test_keras_source_converts_to_tflite_fp32() -> None:
    model = model_record(filename="model.h5", model_format="keras")
    jobs, _events, _s3 = run_convert(
        convert_tflite, _C_TFLITE, model, _tiny_keras_bytes(), params={"precision": "fp32"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99


def _tiny_onnx_bytes() -> bytes:
    inp = helper.make_tensor_value_info("input", onnx.TensorProto.FLOAT, [1, 3, 8, 8])
    out = helper.make_tensor_value_info("output", onnx.TensorProto.FLOAT, [1, 3, 8, 8])
    node = helper.make_node("Relu", ["input"], ["output"])
    graph = helper.make_graph([node], "g", [inp], [out])
    proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    proto.ir_version = 9
    onnx.checker.check_model(proto)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.onnx"
        onnx.save(proto, str(path))
        return path.read_bytes()


def test_onnx_source_converts_to_tflite_via_onnx2tf() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, events, _s3 = run_convert(
        convert_tflite, _C_TFLITE, model, _tiny_onnx_bytes(), params={"precision": "fp32"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99
    stages = {e.stage for e in events.events}
    assert stages == {"Loading model", "Converting to TensorFlow Lite", "Checking outputs match"}


def test_torch_statedict_source_is_refused_cleanly() -> None:
    import io

    model = model_record(filename="model.pt", model_format="torch")
    buffer = io.BytesIO()
    torch.save({"w": torch.randn(3, 4)}, buffer)
    jobs, _events, _s3 = run_convert(convert_tflite, _C_TFLITE, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="Ultralytics' TFLite (LiteRT) export only runs on Linux x86 or macOS, confirmed "
    "empirically; the real worker images are Linux, this is a dev-sandbox-only gap",
)
def test_yolo_source_converts_to_tflite() -> None:
    pytest.importorskip("ultralytics")
    from ultralytics import YOLO

    with tempfile.TemporaryDirectory() as tmp:
        checkpoint = Path(tmp) / "tiny.pt"
        yolo = YOLO("yolo11n.yaml")
        yolo.save(str(checkpoint))
        model_bytes = checkpoint.read_bytes()

    model = model_record(filename="model.pt", model_format="yolo")
    jobs, _events, _s3 = run_convert(
        convert_tflite, _C_TFLITE, model, model_bytes, params={"precision": "fp32"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
