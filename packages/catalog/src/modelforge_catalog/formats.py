"""Model format and family constants shared by every operation."""

from __future__ import annotations

from dataclasses import dataclass

FORMAT: dict[str, str] = {
    "onnx": "ONNX",
    "tflite": "TensorFlow Lite",
    "keras": "Keras",
    "torch": "PyTorch",
    "torchscript": "TorchScript",
    "safetensors": "safetensors",
    "yolo": "YOLO (Ultralytics)",
    "gguf": "GGUF",
    "openvino": "OpenVINO IR",
    "tensorrt": "TensorRT engine",
    "coreml": "Core ML",
    "savedmodel": "TensorFlow SavedModel",
}

FAMILY: dict[str, str] = {
    "vision": "Vision / CNN",
    "llm": "Language model (LLM)",
    "other": "Other",
}

RUNNABLE: tuple[str, ...] = ("onnx", "tflite", "keras", "torch", "torchscript", "yolo")

SHARE_OF_LINEAR: dict[str, float] = {"llm": 0.9, "vision": 0.15, "other": 0.6}


@dataclass(frozen=True, slots=True)
class GgufType:
    value: str
    bits_per_weight: float
    label: str
    perplexity_delta: float


GGUF_TYPES: tuple[GgufType, ...] = (
    GgufType("Q8_0", 8.5, "Q8_0, 8.5 bits, almost lossless", 0.1),
    GgufType("Q6_K", 6.6, "Q6_K, 6.6 bits, very high quality", 0.4),
    GgufType("Q5_K_M", 5.7, "Q5_K_M, 5.7 bits, high quality", 1.0),
    GgufType("Q4_K_M", 4.8, "Q4_K_M, 4.8 bits, recommended balance", 2.8),
    GgufType("Q3_K_M", 3.9, "Q3_K_M, 3.9 bits, small, noticeable loss", 8.0),
    GgufType("Q2_K", 3.4, "Q2_K, 3.4 bits, smallest, large loss", 25.0),
)

_GGUF_BY_VALUE: dict[str, GgufType] = {t.value: t for t in GGUF_TYPES}


def gguf_type(value: str) -> GgufType:
    return _GGUF_BY_VALUE[value]
