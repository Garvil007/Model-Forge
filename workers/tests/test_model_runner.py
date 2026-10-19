"""core.model_runner: unified ModelRunnerProtocol adapter, tested against a tiny ONNX
graph built in-test with onnx.helper (no network fetch)."""

from __future__ import annotations

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper

from core.model_runner import (
    OnnxModelRunner,
    TfliteModelRunner,
    TorchScriptModelRunner,
    UnsupportedRunnerFormatError,
    create_runner,
)


def _write_double_model(path) -> None:
    """A graph computing `y = x * 2` for a `(1, 4)` float input."""
    node = helper.make_node("Mul", ["x", "two"], ["y"])
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    two = helper.make_tensor("two", TensorProto.FLOAT, [1, 4], [2.0, 2.0, 2.0, 2.0])
    graph = helper.make_graph([node], "double", [x], [y], initializer=[two])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=9)
    onnx.checker.check_model(model)
    onnx.save(model, str(path))


def test_onnx_runner_predicts_via_inference_session(tmp_path) -> None:
    model_path = tmp_path / "double.onnx"
    _write_double_model(model_path)

    runner = OnnxModelRunner(model_path)
    output = runner.predict(np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32))

    assert np.allclose(output, [[2.0, 4.0, 6.0, 8.0]])


def test_create_runner_dispatches_to_onnx_adapter(tmp_path) -> None:
    model_path = tmp_path / "double.onnx"
    _write_double_model(model_path)

    runner = create_runner("onnx", model_path)
    output = runner.predict(np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32))

    assert np.allclose(output, [[2.0, 2.0, 2.0, 2.0]])


def test_create_runner_raises_for_unsupported_format(tmp_path) -> None:
    with pytest.raises(UnsupportedRunnerFormatError):
        create_runner("not_a_real_format", tmp_path / "nothing")


def test_tflite_runner_predicts_via_interpreter(tmp_path) -> None:
    tf = pytest.importorskip("tensorflow")

    keras_model = tf.keras.Sequential(
        [tf.keras.layers.Dense(4, use_bias=False, kernel_initializer="identity", input_shape=(4,))]
    )
    converter = tf.lite.TFLiteConverter.from_keras_model(keras_model)
    tflite_bytes = converter.convert()
    model_path = tmp_path / "identity.tflite"
    model_path.write_bytes(tflite_bytes)

    runner = TfliteModelRunner(model_path)
    output = runner.predict(np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32))

    assert np.allclose(output, [[1.0, 2.0, 3.0, 4.0]], atol=1e-4)


def test_create_runner_dispatches_to_tflite_adapter(tmp_path) -> None:
    tf = pytest.importorskip("tensorflow")

    keras_model = tf.keras.Sequential(
        [tf.keras.layers.Dense(4, use_bias=False, kernel_initializer="identity", input_shape=(4,))]
    )
    converter = tf.lite.TFLiteConverter.from_keras_model(keras_model)
    model_path = tmp_path / "identity.tflite"
    model_path.write_bytes(converter.convert())

    runner = create_runner("tflite", model_path)
    output = runner.predict(np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32))

    assert np.allclose(output, [[1.0, 1.0, 1.0, 1.0]], atol=1e-4)


def test_torchscript_runner_predicts_via_jit_module(tmp_path) -> None:
    torch = pytest.importorskip("torch")

    class _Double(torch.nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return x * 2

    module = torch.jit.trace(_Double(), torch.zeros(1, 4))
    model_path = tmp_path / "double.pt"
    torch.jit.save(module, str(model_path))

    runner = TorchScriptModelRunner(model_path)
    output = runner.predict(np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32))

    assert np.allclose(output, [[2.0, 4.0, 6.0, 8.0]])


def test_create_runner_dispatches_to_torchscript_adapter(tmp_path) -> None:
    torch = pytest.importorskip("torch")

    class _Double(torch.nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return x * 2

    module = torch.jit.trace(_Double(), torch.zeros(1, 4))
    model_path = tmp_path / "double.pt"
    torch.jit.save(module, str(model_path))

    runner = create_runner("torchscript", model_path)
    output = runner.predict(np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32))

    assert np.allclose(output, [[2.0, 2.0, 2.0, 2.0]])
