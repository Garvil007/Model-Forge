"""ops.convert_savedmodel: Keras/ONNX -> TensorFlow SavedModel (zipped for upload), using
tiny real models built inside the test and reloaded for real via `tf.saved_model.load`."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import onnx
import onnx.helper as helper
import tensorflow as tf
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_savedmodel

_C_SAVEDMODEL = {op.id: op for op in CONVERTS}["c_savedmodel"]


def _tiny_keras_bytes() -> bytes:
    tf.keras.utils.set_random_seed(0)
    model = tf.keras.Sequential(
        [tf.keras.layers.Input(shape=(4,)), tf.keras.layers.Dense(3, activation="relu")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.h5"
        model.save(str(path))
        return path.read_bytes()


def test_keras_source_exports_to_savedmodel_zip() -> None:
    model = model_record(filename="model.h5", model_format="keras")
    jobs, events, s3 = run_convert(convert_savedmodel, _C_SAVEDMODEL, model, _tiny_keras_bytes())
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99
    assert jobs.calls[-1]["result"]["downloadName"].endswith(".zip")

    key = next(iter(s3.uploaded))
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(s3.uploaded[key])) as archive:
            archive.extractall(tmp)
        reloaded = tf.saved_model.load(tmp)
        assert "serve" in reloaded.signatures


def _tiny_onnx_bytes() -> bytes:
    inp = helper.make_tensor_value_info("input", onnx.TensorProto.FLOAT, [1, 4])
    out = helper.make_tensor_value_info("output", onnx.TensorProto.FLOAT, [1, 4])
    node = helper.make_node("Relu", ["input"], ["output"])
    graph = helper.make_graph([node], "g", [inp], [out])
    proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    proto.ir_version = 9
    onnx.checker.check_model(proto)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.onnx"
        onnx.save(proto, str(path))
        return path.read_bytes()


def test_onnx_source_exports_to_savedmodel_via_onnx2tf() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _events, s3 = run_convert(convert_savedmodel, _C_SAVEDMODEL, model, _tiny_onnx_bytes())
    assert jobs.calls[-1]["status"] == "succeeded"

    key = next(iter(s3.uploaded))
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(s3.uploaded[key])) as archive:
            archive.extractall(tmp)
        reloaded = tf.saved_model.load(tmp)
        assert len(reloaded.signatures) >= 1
