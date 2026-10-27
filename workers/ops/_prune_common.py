"""Shared plumbing for the Pruning-tab ops (`prune_magnitude.py`, `prune_24.py`):
raw-tensor load/save across torch state_dict / safetensors / ONNX initializers / Keras,
sparsity + parameter-count + median-latency measurement, and the download -> prune ->
[fine-tune] -> measure -> upload -> job-status runner both of those ops share.
(`prune_structured.py` needs torch-pruning/TF-MOT model surgery instead of tensor
masking, so it has its own runner.)

Magnitude and 2:4 pruning zero out individual weight values and need no forward pass to
do it, so they work directly on raw tensors for every declared source format — torch
state_dict, safetensors, ONNX initializers, Keras weights — none of which need a runnable
architecture (the `load_raw_tensors`/`save_raw_tensors` pair below). Fine-tuning to
recover accuracy is a different story: it needs real gradients through a real forward
pass, which only exists for formats with a loadable architecture. Of this tab's declared
source formats, only Keras (`tf.keras.models.load_model`) has one — a bare PyTorch
`torch` state_dict, raw `safetensors` weights, and ONNX initializers carry no architecture
to run, the same constraint `workers/ops/fp_cast.py`/`_convert_common.require_hf_repo_id`
already document for other ops. Requesting `finetune` against those three formats
degrades to a clean skip (noted in the result) rather than failing the job — see
`docs/PROGRESS.md`'s Day 15 entry for this documented gap.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.records import ModelRecord
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import UnsupportedFormatError, not_measured, s3_client

_NOT_MEASURED = "not measured"
_LATENCY_ITERATIONS = 20

_SUFFIX_FOR_FORMAT = {
    "torch": ".pt", "safetensors": ".safetensors", "onnx": ".onnx", "keras": ".h5",
}


# --------------------------------------------------------------------------- raw tensors


def _is_prunable(name: str, array: np.ndarray) -> bool:
    """Magnitude/2:4 pruning targets weight matrices, not biases or norm scale/shift
    vectors — 1-D tensors are left untouched, matching the prototype's framing of
    pruning as removing *weights*, and because a 1-D tensor can't carry a 2:4 pattern
    meaningfully along a "group of 4" axis."""
    return (
        array.ndim >= 2
        and np.issubdtype(array.dtype, np.floating)
        and "bias" not in name.lower()
    )


def load_raw_tensors(path: Path, model_format: str) -> dict[str, np.ndarray]:
    if model_format == "torch":
        import torch

        state_dict = torch.load(path, map_location="cpu", weights_only=True)
        return {name: tensor.detach().cpu().numpy() for name, tensor in state_dict.items()}
    if model_format == "safetensors":
        from safetensors.numpy import load_file

        return dict(load_file(str(path)))
    if model_format == "onnx":
        import onnx
        from onnx import numpy_helper

        model = onnx.load(str(path))
        return {init.name: numpy_helper.to_array(init) for init in model.graph.initializer}
    if model_format == "keras":
        import tensorflow as tf

        model = tf.keras.models.load_model(str(path), compile=False, safe_mode=True)
        return {variable.name: variable.numpy() for variable in model.weights}
    raise UnsupportedFormatError(f"no raw-tensor path for format {model_format!r}")


def save_raw_tensors(
    path_in: Path, path_out: Path, model_format: str, tensors: dict[str, np.ndarray]
) -> None:
    """Writes `tensors` back over a copy of `path_in`'s structure — dense (zeroed-but-
    full-shape) for every format: safetensors has no native sparse tensor type, ONNX
    initializers must match their original shape, and Keras `Variable.assign` requires
    it. Only the `torch` path (`_save_torch_sparse` in `prune_magnitude.py`) can
    actually shrink the file via real sparse storage; the other three formats' "sparse"
    option is therefore an estimate, not a measured result — documented in
    `docs/PROGRESS.md`."""
    if model_format == "safetensors":
        from safetensors.numpy import save_file

        save_file(tensors, str(path_out))
        return
    if model_format == "onnx":
        import onnx
        from onnx import numpy_helper

        model = onnx.load(str(path_in))
        by_name = {init.name: init for init in model.graph.initializer}
        for name, array in tensors.items():
            if name in by_name:
                by_name[name].CopyFrom(numpy_helper.from_array(array, name))
        onnx.save(model, str(path_out))
        return
    if model_format == "keras":
        import tensorflow as tf

        model = tf.keras.models.load_model(str(path_in), compile=False, safe_mode=True)
        by_name = {variable.name: variable for variable in model.weights}
        for name, array in tensors.items():
            if name in by_name:
                by_name[name].assign(array)
        model.save(str(path_out))
        return
    raise UnsupportedFormatError(f"no raw-tensor save path for format {model_format!r}")


# -------------------------------------------------------------------------- measurement


def magnitude_threshold(values: np.ndarray, sparsity_fraction: float) -> float:
    if values.size == 0 or sparsity_fraction <= 0:
        return -1.0
    return float(np.quantile(np.abs(values), min(sparsity_fraction, 1.0)))


def apply_global_magnitude_mask(
    tensors: dict[str, np.ndarray], sparsity_fraction: float
) -> dict[str, np.ndarray]:
    prunable = {name: array for name, array in tensors.items() if _is_prunable(name, array)}
    all_values = (
        np.concatenate([array.reshape(-1) for array in prunable.values()])
        if prunable
        else np.array([])
    )
    threshold = magnitude_threshold(all_values, sparsity_fraction)
    pruned = dict(tensors)
    for name, array in prunable.items():
        pruned[name] = np.where(np.abs(array) <= threshold, 0.0, array).astype(array.dtype)
    return pruned


def apply_per_layer_magnitude_mask(
    tensors: dict[str, np.ndarray], sparsity_fraction: float
) -> dict[str, np.ndarray]:
    pruned = dict(tensors)
    for name, array in tensors.items():
        if not _is_prunable(name, array):
            continue
        threshold = magnitude_threshold(array.reshape(-1), sparsity_fraction)
        pruned[name] = np.where(np.abs(array) <= threshold, 0.0, array).astype(array.dtype)
    return pruned


def apply_24_mask(tensors: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Zeroes the 2 smallest-magnitude of every contiguous group of 4 values along each
    prunable tensor's last axis — the "2:4" pattern NVIDIA's sparse tensor cores exploit.
    Tensors whose last-axis length isn't a multiple of 4 are left unpruned (no clean
    group-of-4 tiling), reflected in the caller's sparsity measurement rather than an
    error."""
    pruned = dict(tensors)
    for name, array in tensors.items():
        if not _is_prunable(name, array) or array.shape[-1] % 4 != 0:
            continue
        reshaped = array.reshape(*array.shape[:-1], -1, 4)
        order = np.argsort(np.abs(reshaped), axis=-1)
        keep_mask = order >= 2  # keep the 2 largest-magnitude of each group of 4
        pruned[name] = (
            np.where(keep_mask, reshaped, 0.0).reshape(array.shape).astype(array.dtype)
        )
    return pruned


def measure_sparsity(tensors: dict[str, np.ndarray]) -> tuple[float, int, int]:
    """Returns `(sparsity_fraction, total_params, nonzero_params)` over every tensor
    (not just the prunable ones), matching how `param_count` is reported elsewhere —
    pruning zeroes values in place, it doesn't change a dense tensor's element count."""
    total = 0
    zero = 0
    for array in tensors.values():
        total += array.size
        zero += int(np.count_nonzero(array == 0))
    sparsity = zero / total if total else 0.0
    return sparsity, total, total - zero


def measure_latency_ms(predict: Callable[[np.ndarray], Any], sample: np.ndarray) -> float | None:
    """Median wall-clock latency over `_LATENCY_ITERATIONS` calls to `predict`, or
    `None` if even one call raises (e.g. the sample shape doesn't fit) — a latency
    measurement is best-effort, like `core.similarity.compare_runs`, never a job
    failure."""
    try:
        predict(sample)  # warm-up, excluded from the measurement
        samples_ms = []
        for _ in range(_LATENCY_ITERATIONS):
            start = time.perf_counter()
            predict(sample)
            samples_ms.append((time.perf_counter() - start) * 1000)
        return float(np.median(samples_ms))
    except Exception:  # noqa: BLE001 — best-effort measurement, never fails the job
        return None


def onnx_latency_fn(path: Path) -> tuple[Callable[[np.ndarray], Any], np.ndarray]:
    import onnxruntime

    session = onnxruntime.InferenceSession(str(path))
    model_input = session.get_inputs()[0]
    shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in model_input.shape] or [1]
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)

    def _predict(batch: np.ndarray) -> Any:
        return session.run(None, {model_input.name: batch})

    return _predict, sample


def keras_latency_fn(model: Any) -> tuple[Callable[[np.ndarray], Any], np.ndarray] | None:
    input_shape = getattr(model, "input_shape", None)
    if input_shape is None:
        return None
    shape = tuple(1 if d is None else d for d in input_shape)
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)

    def _predict(batch: np.ndarray) -> Any:
        return model.predict(batch, verbose=0)

    return _predict, sample


# --------------------------------------------------------------------------- job runner


def input_suffix(model_format: str, filename: str) -> str:
    return Path(filename).suffix or _SUFFIX_FOR_FORMAT.get(model_format, "")


PruneFn = Callable[[Path, Path, ModelRecord, dict[str, Any]], dict[str, Any]]
# prune_fn(local_in, local_out, model, params) -> metrics dict with at least
# "sparsity_before", "sparsity_after", "params_total", "params_nonzero_after",
# "latency_ms_before", "latency_ms_after" (either latency key may be None).

FineTuneFn = Callable[
    [Path, ModelRecord, dict[str, Any], str, str, JobEventRepository, Any, Any, str],
    "str | None",
]
# finetune_fn(local_out, model, params, user_id, job_id, event_repo, control, s3,
#             results_bucket) -> a skip-reason string, or None if fine-tuning ran.


def run_prune_op(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    prune_fn: PruneFn,
    finetune_fn: FineTuneFn | None,
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

    tmpdir = tempfile.mkdtemp(prefix="mf-prune-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            uploads_bucket=uploads_bucket, results_bucket=results_bucket, prune_fn=prune_fn,
            finetune_fn=finetune_fn, download_name_tag=download_name_tag,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, uploads_bucket: str, results_bucket: str, prune_fn: PruneFn,
    finetune_fn: FineTuneFn | None, download_name_tag: str,
) -> None:
    model = models.get(user_id, model_id)
    local_in = tmpdir / f"input{input_suffix(model.format, model.filename)}"
    local_out = tmpdir / f"output{input_suffix(model.format, model.filename)}"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    event_repo.append(user_id, job_id, stage="Scoring weights", message="Scoring weight importance")
    control.check()

    event_repo.append(user_id, job_id, stage="Pruning", message="Applying pruning mask")
    try:
        metrics = prune_fn(local_in, local_out, model, params)
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
        if finetune_fn is None:
            skip_reason = (
                "fine-tuning needs a runnable architecture; not available for this format"
            )
        else:
            try:
                skip_reason = finetune_fn(
                    local_out, model, params, user_id, job_id, event_repo, control, s3,
                    results_bucket,
                )
            except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
                raise
            except Exception as error:  # noqa: BLE001 — degrade, don't fail the whole job
                skip_reason = f"fine-tuning failed, keeping the pruned-but-not-tuned model: {error}"
    control.check()

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy", message="Measuring sparsity and latency"
    )
    control.check()

    output_bytes = local_out.stat().st_size
    download_name = f"{Path(model.filename).stem}_{download_name_tag}{local_out.suffix}"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(local_out), results_bucket, s3_key)

    display_metrics = {
        "Sparsity": f"{metrics['sparsity_before']:.1%} -> {metrics['sparsity_after']:.1%}",
        "Parameter count": (
            f"{metrics['params_total']:,} total, "
            f"{metrics['params_nonzero_after']:,} nonzero after pruning"
        ),
        "Median latency": _format_latency(
            metrics.get("latency_ms_before"), metrics.get("latency_ms_after")
        ),
    }
    if skip_reason:
        display_metrics["Fine-tuning"] = f"skipped ({skip_reason})"
    elif params.get("finetune"):
        display_metrics["Fine-tuning"] = "completed"

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": display_metrics,
            "measuredOnValidation": False,
            "speedNote": metrics.get("speed_note"),
            "s3Key": s3_key,
        },
    )


def _format_latency(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return f"{_NOT_MEASURED} (no runnable architecture for this format)"
    return f"{before:.2f} ms -> {after:.2f} ms"


__all__ = [
    "FineTuneFn",
    "PruneFn",
    "UnsupportedFormatError",
    "apply_24_mask",
    "apply_global_magnitude_mask",
    "apply_per_layer_magnitude_mask",
    "input_suffix",
    "keras_latency_fn",
    "load_raw_tensors",
    "magnitude_threshold",
    "measure_latency_ms",
    "measure_sparsity",
    "not_measured",
    "onnx_latency_fn",
    "run_prune_op",
    "save_raw_tensors",
]
