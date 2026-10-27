"""Shared plumbing for the Low-rank tab ops (`lowrank_svd.py`, `lowrank_tucker.py`):
tensor-level truncated SVD / Tucker-2 / CP factorization, per-layer rank/param-saving
bookkeeping, and the download -> decompose -> [fine-tune] -> measure -> upload ->
job-status runner both ops share.

Both ops factor individual weight tensors directly inside a `torch` state_dict or raw
`safetensors` weights — swapping one big tensor for two (SVD) or a core-plus-factors
group (Tucker-2/CP) under suffixed keys — rather than performing graph surgery on a
running `nn.Module`. That is a genuine, measurable parameter/file-size reduction for
these two name->tensor formats (the same class of real effect `prune_magnitude.py`'s
`torch` sparse-tensor path gets for free from a native sparse type), but the result is a
state dict only an architecture written to expect the new suffixed keys could load back
into a forward pass — the same category of limitation `prune_structured.py`'s module
docstring documents for formats with no traceable graph. ONNX (rewiring Gemm/MatMul
nodes) and Keras (rebuilding `Dense`/`Conv2D` layers at new shapes) would need real
graph/model surgery neither op performs yet, so both raise `UnsupportedFormatError` for
those formats — failing the job cleanly with `unsupported_operator` rather than quietly
producing a same-shape file with no actual size reduction. Documented as a known gap in
`docs/PROGRESS.md`'s Day 16 entry.

Fine-tuning (`params["finetune"]`) is NOT wired for either op, for the same reason
`prune_magnitude.py` documents: a bare `torch` state_dict or raw `safetensors` weights
carry no runnable architecture for PyTorch autograd to fine-tune through.
`finetune=true` degrades to a clean, noted skip rather than failing the job.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import UnsupportedFormatError, s3_client
from ._prune_common import input_suffix, load_raw_tensors
from ._prune_common import save_raw_tensors as _save_raw_tensors_generic

_RAW_TENSOR_FORMATS = ("torch", "safetensors")

_ATTENTION_NAME_HINTS = (
    "attn", "attention", "q_proj", "k_proj", "v_proj", "out_proj",
    "query", "key", "value", "self_attn",
)


# --------------------------------------------------------------------------- selection


def is_attention_name(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _ATTENTION_NAME_HINTS)


def is_linear_weight(name: str, array: np.ndarray) -> bool:
    """Candidate for SVD: a 2-D floating weight matrix, not a bias vector — the raw-
    tensor equivalent of an `nn.Linear`/Dense layer's weight."""
    is_floating = np.issubdtype(array.dtype, np.floating)
    return array.ndim == 2 and is_floating and "bias" not in name.lower()


def is_conv_weight(name: str, array: np.ndarray) -> bool:
    """Candidate for Tucker-2/CP: a 4-D floating `(out, in, kh, kw)` convolution kernel."""
    is_floating = np.issubdtype(array.dtype, np.floating)
    return array.ndim == 4 and is_floating and "bias" not in name.lower()


def save_tensors(
    path_in: Path, path_out: Path, model_format: str, tensors: dict[str, np.ndarray]
) -> None:
    """Saves `tensors` as a brand-new `name -> tensor` file — unlike
    `_prune_common.save_raw_tensors`, which overwrites a copy of `path_in`'s existing
    structure (every key must already exist there), this one must also be able to
    *add* new keys (the `__lowrank_u`/`__lowrank_v`-suffixed factors replacing an
    original key that no longer exists), so `torch` gets its own plain `torch.save` of
    the tensor dict rather than `save_raw_tensors`'s format dispatch."""
    if model_format == "torch":
        import torch

        torch.save({name: torch.from_numpy(array) for name, array in tensors.items()}, path_out)
        return
    if model_format == "safetensors":
        from safetensors.numpy import save_file

        save_file(tensors, str(path_out))
        return
    _save_raw_tensors_generic(path_in, path_out, model_format, tensors)


def require_raw_tensor_format(model_format: str, technique_label: str) -> None:
    if model_format not in _RAW_TENSOR_FORMATS:
        raise UnsupportedFormatError(
            f"{technique_label} needs real graph/model surgery for {model_format!r}, which "
            "isn't implemented yet — only torch and safetensors (plain name->tensor weights) "
            "are supported (see _lowrank_common.py's module docstring)"
        )


# -------------------------------------------------------------------------------- SVD


def choose_svd_rank(
    singular_values: np.ndarray, mode: str, energy_pct: float, rank_pct: float
) -> int:
    max_rank = singular_values.size
    if max_rank == 0:
        return 0
    if mode == "fraction":
        return max(1, min(max_rank, round(max_rank * rank_pct / 100)))
    energy = singular_values.astype(np.float64) ** 2
    total = float(energy.sum())
    if total <= 0:
        return max_rank
    cumulative = np.cumsum(energy) / total
    target = min(max(energy_pct / 100, 0.0), 1.0)
    kept = int(np.searchsorted(cumulative, target) + 1)
    return max(1, min(max_rank, kept))


def factorize_svd(weight: np.ndarray, rank: int) -> tuple[np.ndarray, np.ndarray]:
    """Truncated SVD of a 2-D `(out, in)` weight matrix: `weight ≈ u @ v`, with
    `u` shaped `(out, rank)` and `v` shaped `(rank, in)`, singular values folded in as
    `sqrt(s)` on each side so neither factor needs its own separate scale tensor."""
    u, s, vt = np.linalg.svd(weight.astype(np.float64), full_matrices=False)
    scale = np.sqrt(s[:rank])
    u_scaled = (u[:, :rank] * scale).astype(weight.dtype)
    v_scaled = (scale[:, None] * vt[:rank, :]).astype(weight.dtype)
    return u_scaled, v_scaled


def apply_svd_to_tensors(
    tensors: dict[str, np.ndarray], params: dict[str, Any]
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    mode = params.get("mode", "energy")
    energy_pct = float(params.get("energy", 95))
    rank_pct = float(params.get("rank", 25))
    layers = params.get("layers", "mlp")

    output = dict(tensors)
    reports: list[dict[str, Any]] = []
    for name, array in tensors.items():
        if not is_linear_weight(name, array):
            continue
        if layers == "mlp" and is_attention_name(name):
            continue

        out_dim, in_dim = array.shape
        params_before = out_dim * in_dim
        singular_values = np.linalg.svd(array.astype(np.float64), compute_uv=False)
        rank = choose_svd_rank(singular_values, mode, energy_pct, rank_pct)
        params_after = rank * (out_dim + in_dim)

        if params_after >= params_before:
            reports.append({
                "name": name, "shape": (out_dim, in_dim), "rank": rank,
                "params_before": params_before, "params_after": params_before,
                "skipped": True,
            })
            continue

        u_scaled, v_scaled = factorize_svd(array, rank)
        del output[name]
        output[f"{name}__lowrank_u"] = u_scaled
        output[f"{name}__lowrank_v"] = v_scaled
        reports.append({
            "name": name, "shape": (out_dim, in_dim), "rank": rank,
            "params_before": params_before, "params_after": params_after,
            "skipped": False,
        })
    return output, reports


# ---------------------------------------------------------------------- Tucker-2 / CP


def choose_channel_rank(channels: int, rank_pct: float) -> int:
    return max(1, min(channels, round(channels * rank_pct / 100)))


def factorize_tucker2(
    weight: np.ndarray, rank_out: int, rank_in: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tucker-2 of a `(out, in, kh, kw)` conv kernel: decomposes only the channel modes
    (0 and 1), leaving the spatial modes (kh, kw) full — the stable, widely-used variant
    for conv compression (full Tucker on all four modes is far less stable to fine-tune).
    Returns `(core, factor_out, factor_in)` with `core` shaped `(rank_out, rank_in, kh, kw)`,
    `factor_out` shaped `(out, rank_out)`, `factor_in` shaped `(in, rank_in)`."""
    import tensorly as tl
    from tensorly.decomposition import partial_tucker

    tl.set_backend("numpy")
    (core, factors), _rec_errors = partial_tucker(
        weight.astype(np.float64), modes=[0, 1], rank=[rank_out, rank_in]
    )
    factor_out, factor_in = factors[0], factors[1]
    return (
        core.astype(weight.dtype), factor_out.astype(weight.dtype), factor_in.astype(weight.dtype),
    )


def factorize_cp(
    weight: np.ndarray, rank: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """CP (canonical polyadic) decomposition of a `(out, in, kh, kw)` conv kernel into a
    rank-`rank` sum of outer products of four vectors — smaller than Tucker-2 at the same
    rank, but historically harder to recover accuracy from without fine-tuning. Returns
    `(weights, factor_out, factor_in, factor_kh, factor_kw)`."""
    import tensorly as tl
    from tensorly.decomposition import parafac

    tl.set_backend("numpy")
    weights, factors = parafac(weight.astype(np.float64), rank=rank)
    factor_out, factor_in, factor_kh, factor_kw = factors
    return (
        np.asarray(weights, dtype=weight.dtype),
        factor_out.astype(weight.dtype), factor_in.astype(weight.dtype),
        factor_kh.astype(weight.dtype), factor_kw.astype(weight.dtype),
    )


def apply_tucker_to_tensors(
    tensors: dict[str, np.ndarray], params: dict[str, Any]
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    kind = params.get("kind", "tucker2")
    rank_pct = float(params.get("rank", 30))

    output = dict(tensors)
    reports: list[dict[str, Any]] = []
    for name, array in tensors.items():
        if not is_conv_weight(name, array):
            continue

        out_ch, in_ch, kh, kw = array.shape
        params_before = out_ch * in_ch * kh * kw

        if kind == "cp":
            rank = max(1, min(out_ch, in_ch, round(min(out_ch, in_ch) * rank_pct / 100)))
            params_after = rank * (out_ch + in_ch + kh + kw)
        else:
            rank_out = choose_channel_rank(out_ch, rank_pct)
            rank_in = choose_channel_rank(in_ch, rank_pct)
            params_after = rank_out * rank_in * kh * kw + out_ch * rank_out + in_ch * rank_in

        if params_after >= params_before:
            reports.append({
                "name": name, "shape": (out_ch, in_ch, kh, kw),
                "rank": rank if kind == "cp" else f"{rank_out}x{rank_in}",
                "params_before": params_before, "params_after": params_before, "skipped": True,
            })
            continue

        if kind == "cp":
            weights, factor_out, factor_in, factor_kh, factor_kw = factorize_cp(array, rank)
            del output[name]
            output[f"{name}__cp_weights"] = weights
            output[f"{name}__cp_factor_out"] = factor_out
            output[f"{name}__cp_factor_in"] = factor_in
            output[f"{name}__cp_factor_kh"] = factor_kh
            output[f"{name}__cp_factor_kw"] = factor_kw
            rank_report: Any = rank
        else:
            core, factor_out, factor_in = factorize_tucker2(array, rank_out, rank_in)
            del output[name]
            output[f"{name}__tucker_core"] = core
            output[f"{name}__tucker_factor_out"] = factor_out
            output[f"{name}__tucker_factor_in"] = factor_in
            rank_report = f"{rank_out}x{rank_in}"

        reports.append({
            "name": name, "shape": (out_ch, in_ch, kh, kw), "rank": rank_report,
            "params_before": params_before, "params_after": params_after, "skipped": False,
        })
    return output, reports


# --------------------------------------------------------------------------- job runner


DecomposeFn = Callable[
    [dict[str, np.ndarray], dict[str, Any]], tuple[dict[str, np.ndarray], list[dict[str, Any]]]
]


def run_lowrank_op(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    decompose_fn: DecomposeFn,
    download_name_tag: str,
    job_repo: JobRepository | None = None,
    models_repo: ModelRepository | None = None,
    s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")

    tmpdir = tempfile.mkdtemp(prefix="mf-lowrank-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            uploads_bucket=uploads_bucket, results_bucket=results_bucket,
            decompose_fn=decompose_fn, download_name_tag=download_name_tag,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, uploads_bucket: str, results_bucket: str, decompose_fn: DecomposeFn,
    download_name_tag: str,
) -> None:
    model = models.get(user_id, model_id)
    local_in = tmpdir / f"input{input_suffix(model.format, model.filename)}"
    local_out = tmpdir / f"output{input_suffix(model.format, model.filename)}"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    event_repo.append(
        user_id, job_id, stage="Decomposing layers", message="Factorizing weight tensors"
    )
    try:
        require_raw_tensor_format(model.format, "low-rank factorization")
        tensors = load_raw_tensors(local_in, model.format)
        bytes_before = local_in.stat().st_size
        new_tensors, layer_reports = decompose_fn(tensors, params)
        save_tensors(local_in, local_out, model.format, new_tensors)
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify framework failures for the UI
        code = "unsupported_operator" if isinstance(error, UnsupportedFormatError) else "unknown"
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=40,
            error={"code": code, "message": str(error)},
        )
        return
    control.check()

    skip_reason: str | None = None
    if params.get("finetune"):
        skip_reason = "fine-tuning needs a runnable architecture; not available for this format"
    control.check()

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy",
        message="Measuring parameter counts and file size",
    )
    control.check()

    bytes_after = local_out.stat().st_size
    download_name = f"{Path(model.filename).stem}_{download_name_tag}{local_out.suffix}"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(local_out), results_bucket, s3_key)

    factored = [r for r in layer_reports if not r["skipped"]]
    skipped = [r for r in layer_reports if r["skipped"]]
    params_before_total = sum(r["params_before"] for r in layer_reports)
    params_after_total = sum(r["params_after"] for r in layer_reports)

    display_metrics = {
        "Layers factorized": (
            f"{len(factored)} of {len(layer_reports)} candidate layers "
            f"({len(skipped)} skipped — no parameter saving at that rank)"
        ),
        "Per-layer ranks": ", ".join(f"{r['name']}: rank {r['rank']}" for r in factored) or "none",
        "Parameter count": (
            f"{params_before_total:,} -> {params_after_total:,}" if layer_reports else "unchanged"
        ),
        "File size": f"{bytes_before:,} bytes -> {bytes_after:,} bytes",
    }
    if skip_reason:
        display_metrics["Fine-tuning"] = f"skipped ({skip_reason})"
    elif params.get("finetune"):
        display_metrics["Fine-tuning"] = "completed"

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": bytes_after,
            "downloadName": download_name,
            "metrics": display_metrics,
            "measuredOnValidation": False,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )


__all__ = [
    "DecomposeFn",
    "apply_svd_to_tensors",
    "apply_tucker_to_tensors",
    "choose_channel_rank",
    "choose_svd_rank",
    "factorize_cp",
    "factorize_svd",
    "factorize_tucker2",
    "is_attention_name",
    "is_conv_weight",
    "is_linear_weight",
    "require_raw_tensor_format",
    "run_lowrank_op",
    "save_tensors",
]
