"""ops.convert_openvino: ONNX/Keras/YOLO -> OpenVINO IR (zipped `.xml`/`.bin` pair), plus
the one genuine chain in this Convert-tab implementation: HF safetensors -> ONNX (via
Optimum) -> OpenVINO IR."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import onnx
import onnx.helper as helper
import openvino as ov
import tensorflow as tf
import torch
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_openvino

_C_OPENVINO = {op.id: op for op in CONVERTS}["c_openvino"]


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


def _assert_valid_ir_zip(zip_bytes: bytes) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            archive.extractall(tmp)
        xml_files = list(Path(tmp).rglob("*.xml"))
        assert xml_files, "no .xml found in OpenVINO IR zip"
        compiled = ov.compile_model(str(xml_files[0]))
        out = compiled(np.random.randn(1, 3, 8, 8).astype(np.float32))
        assert next(iter(out.values())).shape == (1, 3, 8, 8)


def test_onnx_source_converts_to_openvino_fp32() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, events, s3 = run_convert(
        convert_openvino, _C_OPENVINO, model, _tiny_onnx_bytes(), params={"precision": "fp32"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert float(metrics["Output similarity"]) > 0.99
    stages = {e.stage for e in events.events}
    assert stages == {"Loading model", "Converting to OpenVINO IR", "Checking outputs match"}

    key = next(iter(s3.uploaded))
    _assert_valid_ir_zip(s3.uploaded[key])


def test_onnx_source_converts_to_openvino_int8_weight_compression() -> None:
    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _events, s3 = run_convert(
        convert_openvino, _C_OPENVINO, model, _tiny_onnx_bytes(), params={"precision": "int8"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    key = next(iter(s3.uploaded))
    _assert_valid_ir_zip(s3.uploaded[key])


def _tiny_keras_bytes() -> bytes:
    tf.keras.utils.set_random_seed(0)
    model = tf.keras.Sequential(
        [tf.keras.layers.Input(shape=(4,)), tf.keras.layers.Dense(3, activation="relu")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.h5"
        model.save(str(path))
        return path.read_bytes()


def test_keras_source_converts_to_openvino() -> None:
    model = model_record(filename="model.h5", model_format="keras")
    jobs, _events, s3 = run_convert(
        convert_openvino, _C_OPENVINO, model, _tiny_keras_bytes(), params={"precision": "fp16"},
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    key = next(iter(s3.uploaded))
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(s3.uploaded[key])) as archive:
            archive.extractall(tmp)
        xml_files = list(Path(tmp).rglob("*.xml"))
        assert xml_files


def test_torch_statedict_source_is_refused_cleanly() -> None:
    model = model_record(filename="model.pt", model_format="torch")
    buffer = io.BytesIO()
    torch.save({"w": torch.randn(3, 4)}, buffer)
    jobs, _events, _s3 = run_convert(convert_openvino, _C_OPENVINO, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_safetensors_without_hf_repo_id_is_refused_cleanly() -> None:
    import safetensors.torch

    model = model_record(filename="model.safetensors", model_format="safetensors", details={})
    buffer = safetensors.torch.save({"w": torch.randn(2, 2)})
    jobs, _events, _s3 = run_convert(convert_openvino, _C_OPENVINO, model, buffer)
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_safetensors_hf_llm_runs_the_two_hop_chain_to_openvino() -> None:
    """The one genuine chain: safetensors (HF repo) -> ONNX (Optimum) -> OpenVINO IR.
    Needs network access to download a tiny public HF model, mirroring the same
    network dependency 'Import from Hugging Face' already has."""
    import safetensors.torch

    model = model_record(
        filename="model.safetensors", model_format="safetensors",
        details={"repoId": "hf-internal-testing/tiny-random-gpt2"},
    )
    buffer = safetensors.torch.save({"w": torch.randn(2, 2)})
    jobs, events, s3 = run_convert(convert_openvino, _C_OPENVINO, model, buffer)
    assert jobs.calls[-1]["status"] == "succeeded"

    chain_messages = [e.message for e in events.events if e.stage == "Converting to OpenVINO IR"]
    assert any("Step 1/2" in m for m in chain_messages)
    assert any("Step 2/2" in m for m in chain_messages)

    key = next(iter(s3.uploaded))
    _assert_valid_ir_zip_shapeless(s3.uploaded[key])


def _assert_valid_ir_zip_shapeless(zip_bytes: bytes) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            archive.extractall(tmp)
        xml_files = list(Path(tmp).rglob("*.xml"))
        assert xml_files
        ov.compile_model(str(xml_files[0]))
