"""Upload classification rules shared by the API and workers.

Mirrors ``docs/ui-prototype.html``'s file-extension maps: model weight files map to a
catalog ``FORMAT`` key (used only as a client-side hint — real detection happens in the
worker by inspecting file contents), dataset files are accepted but not format-detected.
"""

from __future__ import annotations


class UnsupportedFileTypeError(ValueError):
    """Raised when a filename's extension isn't an accepted model or dataset type."""


MODEL_EXTENSION_FORMAT: dict[str, str] = {
    "onnx": "onnx",
    "tflite": "tflite",
    "h5": "keras",
    "hdf5": "keras",
    "keras": "keras",
    "pt": "torch",
    "pth": "torch",
    "bin": "torch",
    "ckpt": "torch",
    "safetensors": "safetensors",
    "gguf": "gguf",
}

DATASET_EXTENSIONS: frozenset[str] = frozenset(
    {"zip", "tar", "csv", "jsonl", "parquet", "txt", "npz", "npy"}
)


def extension_of(filename: str) -> str:
    """The lowercased suffix after the last dot, or "" if there isn't one."""
    _, _, suffix = filename.rpartition(".")
    return suffix.lower()


def classify_extension(filename: str) -> tuple[str, str | None]:
    """Classify a filename as ``("model", format_hint)`` or ``("dataset", None)``.

    Raises :class:`UnsupportedFileTypeError` if the extension is neither a known model
    weight format nor a known dataset format.
    """
    ext = extension_of(filename)
    if ext in MODEL_EXTENSION_FORMAT:
        return "model", MODEL_EXTENSION_FORMAT[ext]
    if ext in DATASET_EXTENSIONS:
        return "dataset", None
    raise UnsupportedFileTypeError(f"unsupported file extension: {ext!r}")
