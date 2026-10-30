"""ops.convert_tensorrt: ONNX/YOLO -> TensorRT engine.

Building (and running) a real engine needs `tensorrt` plus an actual CUDA device, neither
present in this sandbox, so that path is skipped via `pytest.importorskip` (same
convention every other GPU-only op test uses). The int8-refusal and Jetson-bundle paths
don't touch `tensorrt` at all and are exercised for real here.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import onnx
import onnx.helper as helper
import pytest
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_tensorrt

_C_TENSORRT = {op.id: op for op in CONVERTS}["c_tensorrt"]


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


def test_int8_is_refused_cleanly() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _events, _s3 = run_convert(
        convert_tensorrt, _C_TENSORRT, model, _tiny_onnx_bytes(),
        params={"precision": "int8", "gpu": "l4"},
    )
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_jetson_target_bundles_onnx_and_trtexec_command_instead_of_building() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, events, s3 = run_convert(
        convert_tensorrt, _C_TENSORRT, model, _tiny_onnx_bytes(),
        params={"precision": "fp16", "gpu": "jetson"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert metrics["GPU target"] == "Jetson Orin"
    stages = {e.stage for e in events.events}
    assert stages == {"Loading model", "Converting to TensorRT engine", "Checking outputs match"}

    key = next(iter(s3.uploaded))
    with zipfile.ZipFile(io.BytesIO(s3.uploaded[key])) as archive:
        names = set(archive.namelist())
        assert "model.onnx" in names
        assert "trtexec_command.txt" in names
        command = archive.read("trtexec_command.txt").decode()
        assert command.strip() == "trtexec --onnx=model.onnx --saveEngine=model.engine --fp16"


def test_onnx_fp16_builds_and_validates_a_real_engine() -> None:
    pytest.importorskip("tensorrt")
    pytest.importorskip("cuda.cudart")
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _events, s3 = run_convert(
        convert_tensorrt, _C_TENSORRT, model, _tiny_onnx_bytes(),
        params={"precision": "fp16", "gpu": "l4"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    key = next(iter(s3.uploaded))
    with zipfile.ZipFile(io.BytesIO(s3.uploaded[key])) as archive:
        names = set(archive.namelist())
        assert "model.engine" in names
        assert "README.txt" in names
