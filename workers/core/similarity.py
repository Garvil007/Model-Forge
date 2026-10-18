"""Output-similarity check: run the original and the result on the same random inputs and
report how close they are. Shared by every quantization op that can actually execute both
models (ONNX, TorchScript, Keras/TFLite) — ops whose source format has no runnable
architecture (a bare state_dict, raw safetensors weights) skip this and say so.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

RunFn = Callable[[dict[str, np.ndarray]], list[np.ndarray]]

_NOT_MEASURED = "not measured"


def _align_layout(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """If both outputs are 4-D but one looks like the other's NCHW/NHWC transpose, align it."""
    if a.ndim != 4 or b.ndim != 4 or a.shape == b.shape:
        return a, b
    if a.shape == (b.shape[0], b.shape[3], b.shape[1], b.shape[2]):
        return a, np.transpose(b, (0, 3, 1, 2))
    if b.shape == (a.shape[0], a.shape[3], a.shape[1], a.shape[2]):
        return np.transpose(a, (0, 3, 1, 2)), b
    return a, b


def compare_arrays(original: np.ndarray, result: np.ndarray) -> dict[str, str]:
    """Cosine similarity, largest absolute difference, and top-1 agreement between two
    same-input-driven outputs, reported as display-ready strings."""
    original, result = _align_layout(original, result)
    if original.shape != result.shape:
        return {
            "Output similarity": f"{_NOT_MEASURED} (shape mismatch)",
            "Max difference": f"{_NOT_MEASURED} (shape mismatch)",
            "Top-1 agreement": f"{_NOT_MEASURED} (shape mismatch)",
        }

    o = original.astype(np.float64).reshape(-1)
    r = result.astype(np.float64).reshape(-1)
    denom = (np.linalg.norm(o) * np.linalg.norm(r)) or 1.0
    cosine = float(np.dot(o, r) / denom)
    max_diff = float(np.max(np.abs(o - r))) if o.size else 0.0

    flat_original = original.astype(np.float64).reshape(original.shape[0], -1)
    flat_result = result.astype(np.float64).reshape(result.shape[0], -1)
    if flat_original.shape[-1] > 1:
        top1 = float(
            np.mean(np.argmax(flat_original, axis=-1) == np.argmax(flat_result, axis=-1))
        )
    else:
        top1 = 1.0 if max_diff < 1e-3 else 0.0

    return {
        "Output similarity": f"{cosine:.4f}",
        "Max difference": f"{max_diff:.6f}",
        "Top-1 agreement": f"{top1:.4f}",
    }


def compare_runs(
    original_run: RunFn, result_run: RunFn, feeds: dict[str, np.ndarray]
) -> dict[str, str]:
    """Run both callables on the same `feeds` and compare their first output. Any failure
    (shape the model doesn't like, a runtime error) degrades to a "not measured" result
    rather than failing the job — a comparison is best-effort, not a correctness gate."""
    try:
        original_out = original_run(feeds)[0]
        result_out = result_run(feeds)[0]
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return {
            "Output similarity": f"{_NOT_MEASURED} (comparison failed)",
            "Max difference": f"{_NOT_MEASURED} (comparison failed)",
            "Top-1 agreement": f"{_NOT_MEASURED} (comparison failed)",
        }
    return compare_arrays(np.asarray(original_out), np.asarray(result_out))
