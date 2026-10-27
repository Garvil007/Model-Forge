"""p_magnitude: global or per-layer unstructured magnitude pruning — zero out the
smallest-magnitude weights, optionally stored as real sparse tensors (torch only; see
`_save_torch` below) or left dense-but-zeroed (every format).

Works directly on raw tensors via `_prune_common.load_raw_tensors`/`save_raw_tensors`
for all four declared source formats (torch state_dict, safetensors, ONNX initializers,
Keras weights) — magnitude pruning needs no forward pass, just the tensor values.

Fine-tuning (`params["finetune"]`) is NOT wired for this op: none of its declared source
formats carry a runnable architecture with PyTorch-style autograd that
`workers/core/train.py` (built around `torch.autocast`/`GradScaler`/`state_dict`) can
drive — a bare `torch` state_dict and raw `safetensors` weights have no architecture at
all (same constraint `workers/ops/fp_cast.py` documents), ONNX has no autograd, and Keras
is TensorFlow, not PyTorch. `finetune=true` against this op degrades to a clean, noted
skip rather than failing the job. `prune_structured.py`'s YOLO path is where this tab's
`train.py` integration actually lives — see that module's docstring. Documented as a
known gap in `docs/PROGRESS.md`'s Day 15 entry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modelforge_db.records import ModelRecord

from ._prune_common import (
    apply_global_magnitude_mask,
    apply_per_layer_magnitude_mask,
    keras_latency_fn,
    load_raw_tensors,
    measure_latency_ms,
    measure_sparsity,
    onnx_latency_fn,
    run_prune_op,
    save_raw_tensors,
)


def _save_torch(path_out: Path, tensors: dict[str, Any], sparse: bool) -> None:
    """Dense tensors stay `torch.Tensor`; when `sparse` is requested, every tensor that
    actually has zeros becomes a real `torch.sparse_coo_tensor` — the one source format
    here where "sparse storage" genuinely shrinks the saved file rather than being an
    estimate (safetensors/ONNX/Keras have no native sparse tensor type to round-trip
    through; see `_prune_common.save_raw_tensors`'s docstring)."""
    import torch

    output: dict[str, Any] = {}
    for name, array in tensors.items():
        tensor = torch.from_numpy(array)
        if sparse and tensor.dim() >= 2 and torch.count_nonzero(tensor) < tensor.numel():
            output[name] = tensor.to_sparse()
        else:
            output[name] = tensor
    torch.save(output, path_out)


def _latency_fn_for(model_format: str, path: Path) -> tuple[Any, Any] | None:
    """Builds `(predict, sample)` for a model file on disk — `local_in` is never
    overwritten by this op (only `local_out` is written), so the same helper measures
    both the original and the pruned result just by pointing it at a different path."""
    if model_format == "onnx":
        return onnx_latency_fn(path)
    if model_format == "keras":
        import tensorflow as tf

        model = tf.keras.models.load_model(path, compile=False, safe_mode=True)
        return keras_latency_fn(model)
    return None


def _measure_latency(model_format: str, path: Path) -> float | None:
    fn = _latency_fn_for(model_format, path)
    return measure_latency_ms(*fn) if fn else None


def _prune(
    local_in: Path, local_out: Path, model: ModelRecord, params: dict[str, Any]
) -> dict[str, Any]:
    sparsity_fraction = float(params.get("sparsity", 50)) / 100
    scope = params.get("scope", "global")
    storage = params.get("storage", "sparse")

    tensors = load_raw_tensors(local_in, model.format)
    sparsity_before, total_params, _ = measure_sparsity(tensors)
    latency_before = _measure_latency(model.format, local_in)

    mask_fn = apply_global_magnitude_mask if scope == "global" else apply_per_layer_magnitude_mask
    pruned = mask_fn(tensors, sparsity_fraction)
    sparsity_after, _, nonzero_after = measure_sparsity(pruned)

    if model.format == "torch":
        _save_torch(local_out, pruned, sparse=storage == "sparse")
    else:
        save_raw_tensors(local_in, local_out, model.format, pruned)

    latency_after = _measure_latency(model.format, local_out)

    return {
        "sparsity_before": sparsity_before,
        "sparsity_after": sparsity_after,
        "params_total": total_params,
        "params_nonzero_after": nonzero_after,
        "latency_ms_before": latency_before,
        "latency_ms_after": latency_after,
        "speed_note": None,
    }


def run(**kwargs: Any) -> None:
    run_prune_op(prune_fn=_prune, finetune_fn=None, download_name_tag="magnitude", **kwargs)


__all__ = ["run"]
