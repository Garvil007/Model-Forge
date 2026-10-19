"""ops.convert_torchscript: ONNX/YOLO -> TorchScript, using tiny real models built inside
the test and reloaded for real via `torch.jit.load`."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import onnx
import onnx.helper as helper
import torch
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_torchscript

_C_TORCHSCRIPT = {op.id: op for op in CONVERTS}["c_torchscript"]


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


def test_onnx_source_converts_to_torchscript_via_onnx2torch() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, events, _s3 = run_convert(convert_torchscript, _C_TORCHSCRIPT, model, _tiny_onnx_bytes())
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99
    stages = {e.stage for e in events.events}
    assert stages == {"Loading model", "Converting to TorchScript", "Checking outputs match"}

    # the uploaded result must actually be loadable as a real ScriptModule
    key = next(iter(_s3.uploaded))
    scripted = torch.jit.load(io.BytesIO(_s3.uploaded[key]), map_location="cpu")
    with torch.no_grad():
        out = scripted(torch.zeros(1, 4))
    assert out.shape == (1, 4)


def test_torch_statedict_source_is_refused_cleanly() -> None:
    model = model_record(filename="model.pt", model_format="torch")
    buffer = io.BytesIO()
    torch.save({"w": torch.randn(3, 4)}, buffer)
    jobs, _events, _s3 = run_convert(convert_torchscript, _C_TORCHSCRIPT, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_yolo_source_converts_to_torchscript() -> None:
    import pytest

    pytest.importorskip("ultralytics")
    from ultralytics import YOLO

    with tempfile.TemporaryDirectory() as tmp:
        checkpoint = Path(tmp) / "tiny.pt"
        yolo = YOLO("yolo11n.yaml")
        yolo.save(str(checkpoint))
        model_bytes = checkpoint.read_bytes()

    model = model_record(filename="model.pt", model_format="yolo")
    jobs, _events, _s3 = run_convert(convert_torchscript, _C_TORCHSCRIPT, model, model_bytes)
    assert jobs.calls[-1]["status"] == "succeeded"
