"""p_24: 2:4 semi-structured sparsity — zero the 2 smallest-magnitude of every
contiguous group of 4 weights along each prunable tensor's last axis, the pattern
NVIDIA Ampere+ sparse tensor cores accelerate.

Works directly on raw tensors via `_prune_common.apply_24_mask`, same as
`prune_magnitude.py`, for all three declared source formats (torch state_dict,
safetensors, ONNX initializers) — no forward pass needed. Always saved dense: the 2:4
pattern's actual speedup comes from a GPU reading it through `torch.sparse.
to_sparse_semi_structured`/cuSPARSELt at *inference* time on real Ampere+ hardware, not
from a smaller file at rest, so there is no "sparse storage" choice here the way
`p_magnitude` has one.

Fine-tuning is NOT wired, for the same reason `prune_magnitude.py` documents: none of
this op's source formats carry a runnable, PyTorch-autograd-ready architecture.
Documented as a known gap in `docs/PROGRESS.md`'s Day 15 entry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modelforge_db.records import ModelRecord

from ._prune_common import (
    apply_24_mask,
    load_raw_tensors,
    measure_sparsity,
    run_prune_op,
    save_raw_tensors,
)

_SPEED_NOTE = "about 1.4 times faster on Ampere+ GPUs"


def _prune(
    local_in: Path, local_out: Path, model: ModelRecord, params: dict[str, Any]
) -> dict[str, Any]:
    tensors = load_raw_tensors(local_in, model.format)
    sparsity_before, total_params, _ = measure_sparsity(tensors)

    pruned = apply_24_mask(tensors)
    sparsity_after, _, nonzero_after = measure_sparsity(pruned)

    if model.format == "torch":
        import torch

        torch.save({name: torch.from_numpy(array) for name, array in pruned.items()}, local_out)
    else:
        save_raw_tensors(local_in, local_out, model.format, pruned)

    return {
        "sparsity_before": sparsity_before,
        "sparsity_after": sparsity_after,
        "params_total": total_params,
        "params_nonzero_after": nonzero_after,
        "latency_ms_before": None,
        "latency_ms_after": None,
        "speed_note": _SPEED_NOTE,
    }


def run(**kwargs: Any) -> None:
    run_prune_op(prune_fn=_prune, finetune_fn=None, download_name_tag="24sparse", **kwargs)


__all__ = ["run"]
