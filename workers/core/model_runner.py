"""Unifies ONNX Runtime / TFLite / torch / TorchScript inference behind one
`ModelRunnerProtocol.predict(batch) -> array`, so the same evaluator code (`core.evaluators`)
runs against both the original and quantized/converted model.

Factored out of the per-format inference already in `workers/ops/quantize_dynamic.py`
(`_quantize_onnx`'s `onnxruntime.InferenceSession` + `.run`, `_quantize_keras`'s TFLite
`Interpreter` set_tensor/invoke/get_tensor dance) rather than duplicating it — that module
still owns its own synthetic-input generation for output-similarity checks, which is a
different concern from feeding real validation-dataset batches through here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class UnsupportedRunnerFormatError(Exception):
    """Raised when no `ModelRunnerProtocol` adapter exists for a model format."""


class OnnxModelRunner:
    def __init__(self, path: str | Path) -> None:
        import onnxruntime

        self._session = onnxruntime.InferenceSession(str(path))
        self._input_name = self._session.get_inputs()[0].name

    def predict(self, batch: np.ndarray) -> np.ndarray:
        outputs = self._session.run(None, {self._input_name: np.asarray(batch, dtype=np.float32)})
        return np.asarray(outputs[0])


class TfliteModelRunner:
    def __init__(self, path: str | Path) -> None:
        import tensorflow as tf

        self._interpreter = tf.lite.Interpreter(model_path=str(path))
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()[0]
        self._output_details = self._interpreter.get_output_details()[0]

    def predict(self, batch: np.ndarray) -> np.ndarray:
        array = np.asarray(batch).astype(self._input_details["dtype"])
        self._interpreter.set_tensor(self._input_details["index"], array)
        self._interpreter.invoke()
        return np.asarray(self._interpreter.get_tensor(self._output_details["index"]))


class TorchScriptModelRunner:
    def __init__(self, path: str | Path) -> None:
        import torch

        self._torch = torch
        self._module = torch.jit.load(str(path), map_location="cpu")
        self._module.eval()

    def predict(self, batch: np.ndarray) -> np.ndarray:
        with self._torch.no_grad():
            tensor = self._torch.from_numpy(np.asarray(batch, dtype=np.float32))
            output = self._module(tensor)
        return output.numpy() if hasattr(output, "numpy") else np.asarray(output)


_RUNNERS_BY_FORMAT: dict[str, Any] = {
    "onnx": OnnxModelRunner,
    "tflite": TfliteModelRunner,
    "torchscript": TorchScriptModelRunner,
}


def create_runner(model_format: str, path: str | Path) -> Any:
    """Factory returning the right `ModelRunnerProtocol` adapter for `model_format`."""
    runner_class = _RUNNERS_BY_FORMAT.get(model_format)
    if runner_class is None:
        raise UnsupportedRunnerFormatError(
            f"no ModelRunnerProtocol adapter for format {model_format!r}"
        )
    return runner_class(path)


__all__ = [
    "OnnxModelRunner",
    "TfliteModelRunner",
    "TorchScriptModelRunner",
    "UnsupportedRunnerFormatError",
    "create_runner",
]
