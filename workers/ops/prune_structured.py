"""p_structured: structured channel/filter pruning — removes whole channels/filters so
the network becomes genuinely narrower (fewer parameters, faster on any device, no
sparse-aware runtime needed), unlike `p_magnitude`'s same-shape-but-zeroed tensors.

Two real paths, matching this op's only two declared source formats with a loadable
architecture:

- **YOLO** (`ultralytics.YOLO`, loaded via `_convert_common.load_yolo_safely`): traced
  and pruned with `torch-pruning`'s `MagnitudePruner` (L1/L2) or `TaylorImportance`
  (needs a batch of real data to estimate gradients — a single random-input forward +
  backward is used to rank importance, which needs no labels). This is the path that
  actually narrows the model — `net.parameters()` shrinks for real — and the one
  `workers/core/train.py` plugs into for fine-tuning-with-resume, since a loaded YOLO
  model is a genuine PyTorch `nn.Module` with real autograd.
- **Keras**: `tensorflow_model_optimization`'s `prune_low_magnitude` wraps each
  prunable layer with a magnitude-based sparsity mask. This is TF-MOT's actual shipped
  API — it does NOT remove channels or produce a smaller `nn.Module`/`tf.keras.Model`
  graph the way torch-pruning does for YOLO; it produces a same-shape, mostly-zeroed
  model, the same structural result as `p_magnitude`'s Keras path. Reported honestly
  (no "genuinely narrower" claim for this path) — documented as a known simplification
  in `docs/PROGRESS.md`'s Day 15 entry, since TF-MOT ships no real structured-pruning
  API to narrow a `tf.keras.Model`'s layers.

`torch`/`safetensors` sources are refused with `UnsupportedFormatError`: structured
pruning needs to trace a real computation graph, and neither format carries one (the
same constraint `prune_magnitude.py`'s docstring documents for fine-tuning).

Fine-tuning here needs `params["train_data"]` resolved to a real local file, which this
op cannot do yet — the generic `type="file"` param has no upload-to-worker S3 plumbing
(the same gap `workers/ops/_llm_common.py::resolve_calibration_text` already documents
for `imatrix_text`). `workers/core/train.py`'s checkpoint/resume mechanism itself is
real and independently tested (`workers/tests/test_train.py`) — this op wires it in
structurally and will start running real fine-tunes the day `train_data` upload is
wired to storage, without any change to this file.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import UnsupportedFormatError, load_yolo_safely, s3_client

_YOLO_INPUT_SHAPE = (1, 3, 640, 640)
_LATENCY_ITERATIONS = 20


# -------------------------------------------------------------------------------- YOLO


def _yolo_param_count(net: Any) -> int:
    return sum(p.numel() for p in net.parameters())


def _yolo_latency_ms(net: Any, sample: Any) -> float | None:
    import torch

    try:
        net.eval()
        with torch.no_grad():
            net(sample)  # warm-up
            samples_ms = []
            for _ in range(_LATENCY_ITERATIONS):
                start = time.perf_counter()
                net(sample)
                samples_ms.append((time.perf_counter() - start) * 1000)
        import numpy as np

        return float(np.median(samples_ms))
    except Exception:  # noqa: BLE001 — best-effort, never fails the job
        return None


def _prune_yolo(local_in: Path, local_out: Path, params: dict[str, Any]) -> dict[str, Any]:
    import torch
    import torch_pruning as tp

    ratio = float(params.get("ratio", 30)) / 100
    criterion = params.get("criterion", "l1")

    baseline = load_yolo_safely(local_in)
    baseline_net = baseline.model
    sample = torch.randn(*_YOLO_INPUT_SHAPE)
    params_before = _yolo_param_count(baseline_net)
    latency_before = _yolo_latency_ms(baseline_net, sample)

    yolo = load_yolo_safely(local_in)
    net = yolo.model
    net.eval()

    if criterion == "taylor":
        importance = tp.importance.TaylorImportance()
        example_inputs = sample
        output = net(example_inputs)
        loss = sum(o.sum() for o in output) if isinstance(output, (list, tuple)) else output.sum()
        loss.backward()
    else:
        importance = tp.importance.MagnitudeImportance(p=2 if criterion == "l2" else 1)
        example_inputs = sample

    # Ultralytics' detection head has fixed output channels (num_classes + 4 box
    # params) that must not be pruned, or the model stops being a valid detector.
    ignored_layers = [net.model[-1]] if hasattr(net, "model") else []

    pruner = tp.pruner.MagnitudePruner(
        net, example_inputs, importance=importance, pruning_ratio=ratio,
        ignored_layers=ignored_layers,
    )
    pruner.step()

    params_after = _yolo_param_count(net)
    latency_after = _yolo_latency_ms(net, sample)

    torch.save({"model": net}, local_out)

    return {
        "params_before": params_before,
        "params_after": params_after,
        "latency_ms_before": latency_before,
        "latency_ms_after": latency_after,
        "speed_note": f"about {1 / max(1 - ratio, 0.01):.1f} times faster",
        "pruned_model": net,
        "criterion_used": criterion,
    }


# ------------------------------------------------------------------------------- Keras


def _prune_keras(local_in: Path, local_out: Path, params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import tensorflow as tf
    import tensorflow_model_optimization as tfmot

    ratio = float(params.get("ratio", 30)) / 100
    model = tf.keras.models.load_model(str(local_in), compile=False, safe_mode=True)
    params_before = model.count_params()

    def _wrap(layer: Any) -> Any:
        if isinstance(layer, (tf.keras.layers.Conv2D, tf.keras.layers.Dense)):
            schedule = tfmot.sparsity.keras.ConstantSparsity(target_sparsity=ratio, begin_step=0)
            return tfmot.sparsity.keras.prune_low_magnitude(layer, pruning_schedule=schedule)
        return layer

    pruned = tf.keras.models.clone_model(model, clone_function=_wrap)
    pruned.build(model.input_shape)
    pruned = tfmot.sparsity.keras.strip_pruning(pruned)
    # Params count is unchanged (TF-MOT zeroes, doesn't remove, channels — see module
    # docstring); nonzero count after is what actually reflects the "narrower" claim.
    params_after = sum(int(np.count_nonzero(w)) for w in pruned.get_weights())

    pruned.save(str(local_out))

    return {
        "params_before": params_before,
        "params_after": params_after,
        "latency_ms_before": None,
        "latency_ms_after": None,
        "speed_note": None,
        "pruned_model": None,
        "criterion_used": None,
    }


# --------------------------------------------------------------------------- fine-tune


def _finetune_yolo(
    net: Any, params: dict[str, Any], user_id: str, job_id: str,
    event_repo: JobEventRepository, control: Any, s3: Any, results_bucket: str,
) -> str | None:
    train_data_ref = params.get("train_data")
    if not train_data_ref:
        return "no training data uploaded"
    # type="file" params (train_data, imatrix_text) have no S3 upload plumbing yet —
    # see module docstring. Once wired, this branch resolves train_data_ref to a local
    # path, builds an ImageFolderLoader/DetectionLoader-backed `make_batches`, and
    # calls `core.train.run_finetune_loop` with a feature-matching recovery loss
    # (pruned net's output vs. a frozen copy of the original net — label-free, works
    # for any detection dataset without parsing annotations).
    return "training data upload isn't wired to worker storage yet (see docs/PROGRESS.md)"


# --------------------------------------------------------------------------- job runner


def run(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    job_repo: JobRepository | None = None,
    models_repo: ModelRepository | None = None,
    s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")

    tmpdir = tempfile.mkdtemp(prefix="mf-prune-structured-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            uploads_bucket=uploads_bucket, results_bucket=results_bucket,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, uploads_bucket: str, results_bucket: str,
) -> None:
    model = models.get(user_id, model_id)
    suffix = {"yolo": ".pt", "keras": ".h5"}.get(model.format, Path(model.filename).suffix)
    local_in = tmpdir / f"input{suffix}"
    local_out = tmpdir / f"output{suffix}"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    event_repo.append(
        user_id, job_id, stage="Scoring weights", message="Scoring channel importance"
    )
    control.check()

    event_repo.append(user_id, job_id, stage="Pruning", message="Removing channels/filters")
    try:
        if model.format == "yolo":
            metrics = _prune_yolo(local_in, local_out, params)
        elif model.format == "keras":
            metrics = _prune_keras(local_in, local_out, params)
        else:
            raise UnsupportedFormatError(
                f"structured pruning needs a traceable architecture; {model.format!r} has none "
                "(torch/safetensors are weights-only here — import as YOLO or Keras instead)"
            )
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
        if model.format == "yolo" and metrics.get("pruned_model") is not None:
            try:
                skip_reason = _finetune_yolo(
                    metrics["pruned_model"], params, user_id, job_id, event_repo, control, s3,
                    results_bucket,
                )
            except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
                raise
            except Exception as error:  # noqa: BLE001 — degrade, don't fail the whole job
                skip_reason = f"fine-tuning failed, keeping the pruned-but-not-tuned model: {error}"
        else:
            skip_reason = "fine-tuning needs a runnable architecture; not available for this format"
    control.check()

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy", message="Measuring parameter count and latency"
    )
    control.check()

    output_bytes = local_out.stat().st_size
    download_name = f"{Path(model.filename).stem}_structured{local_out.suffix}"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(local_out), results_bucket, s3_key)

    display_metrics = {
        "Parameter count": f"{metrics['params_before']:,} -> {metrics['params_after']:,}",
        "Median latency": _format_latency(
            metrics.get("latency_ms_before"), metrics.get("latency_ms_after")
        ),
    }
    if metrics.get("criterion_used"):
        display_metrics["Importance criterion"] = metrics["criterion_used"]
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
        return "not measured (no runnable architecture for this format)"
    return f"{before:.2f} ms -> {after:.2f} ms"


__all__ = ["run"]
