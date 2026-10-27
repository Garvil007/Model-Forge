"""Shared fine-tuning loop for pruning/low-rank/distillation ops — the `finetune`/
`train_data`/`epochs` params every one of those techniques declares via
`packages/catalog/src/modelforge_catalog/methods.py::_finetune_params()`, and the
"Fine-tuning" stage `job_stages.py` already inserts for them.

Owns the parts that are identical regardless of *what* is being fine-tuned:

- Mixed-precision forward/backward (`torch.autocast` + `GradScaler` — `GradScaler` is a
  no-op when `enabled=False`, which this module sets whenever `device != "cuda"`).
- Exactly one `JobEvent(stage="Fine-tuning", ...)` per *completed* epoch, not per batch,
  because `apps/api/app/services.py::_stage_dicts()` reconstructs the UI's `epoch`/
  `totalEpochs` purely by counting "Fine-tuning" events, capped at the stage's declared
  `epochs`. Emitting more than one per epoch would desync that counter from reality.
- `control.check()` once per epoch, so cooperative cancellation/timeout/spot-
  interruption (`workers/core/runner.py::JobControl`) can stop the loop between epochs.
- A checkpoint (model + optimizer state + the index of the last *completed* epoch)
  written to S3 after every epoch, and loaded back in before the first epoch runs —
  the mechanism behind "fine-tuning run resumes after killing the worker":
  `runner.py::_handle_spot_interruption` already requeues the same `job_id` once on
  `SpotInterruptedError`; the op's second attempt calls this same `run_finetune_loop`,
  which finds the prior attempt's checkpoint under `checkpoint_key` and resumes at
  `last_completed_epoch + 1` instead of epoch 0.

What this module does NOT own: the dataset, the batch shape, or the loss function —
an image classifier's cross-entropy loss looks nothing like a causal-LM's next-token
loss. Those are the calling op's concern, passed in as a `train_step` closure and a
`make_batches` factory (called fresh each epoch, since the `core.datasets.*` loaders
are single-pass iterables).
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# (model, batch) -> scalar loss tensor. The op builds this closure so it alone knows
# how to unpack a batch and which loss function applies to its task.
TrainStepFn = Callable[[Any, Any], Any]

# Called once per epoch; returns a fresh iterable of batches (core.datasets.* loaders
# are single-pass, so re-iterating the same object would yield nothing on epoch 2+).
BatchIterableFactory = Callable[[], Iterable[Any]]


@dataclass(frozen=True, slots=True)
class FineTuneConfig:
    epochs: int
    checkpoint_key: str
    mixed_precision: bool = True
    grad_clip: float | None = 1.0


@dataclass(frozen=True, slots=True)
class FineTuneResult:
    epochs_run: int
    final_loss: float | None
    resumed_from_epoch: int


def _device_type(device: str) -> str:
    return "cuda" if device == "cuda" else "cpu"


def save_checkpoint(path: Path, model: Any, optimizer: Any, completed_epoch: int) -> None:
    """Checkpoint contents are this worker's own output, not user-controlled input —
    unlike a user-uploaded model file (see `core.datasets.base.load_npy_safely`'s
    `allow_pickle` refusal) — so a plain `torch.save`/`torch.load` round trip is fine."""
    import torch

    torch.save(
        {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "completed_epoch": completed_epoch,
        },
        path,
    )


def load_checkpoint(path: Path, model: Any, optimizer: Any) -> int:
    """Loads a checkpoint written by `save_checkpoint` and returns the epoch to resume
    at (last completed + 1). `weights_only=True` even though this checkpoint is our own
    output, not user-controlled input — it round-trips cleanly (tensors + plain dicts/
    ints) and costs nothing to keep restricted."""
    import torch

    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model_state"])
    optimizer.load_state_dict(checkpoint["optimizer_state"])
    return int(checkpoint["completed_epoch"]) + 1


def _try_resume(
    *, s3: Any, bucket: str, checkpoint_key: str, local_path: Path, model: Any, optimizer: Any
) -> int:
    try:
        s3.download_file(bucket, checkpoint_key, str(local_path))
    except Exception:  # noqa: BLE001 — no checkpoint yet (first attempt) is the common case
        return 0
    return load_checkpoint(local_path, model, optimizer)


def run_finetune_loop(
    *,
    model: Any,
    optimizer: Any,
    make_batches: BatchIterableFactory,
    train_step: TrainStepFn,
    config: FineTuneConfig,
    user_id: str,
    job_id: str,
    event_repo: Any,
    control: Any,
    s3: Any,
    results_bucket: str,
    device: str = "cpu",
) -> FineTuneResult:
    """Runs (or resumes) `config.epochs` epochs of fine-tuning, emitting one JobEvent and
    one S3 checkpoint per completed epoch. See the module docstring for the full
    contract. Caller owns the model/optimizer lifecycle before and after this call."""
    import torch

    device_type = _device_type(device)
    scaler = torch.amp.GradScaler(
        device_type, enabled=config.mixed_precision and device_type == "cuda"
    )

    tmpdir = Path(tempfile.mkdtemp(prefix="mf-ckpt-"))
    local_ckpt = tmpdir / "checkpoint.pt"
    try:
        epoch_start = _try_resume(
            s3=s3, bucket=results_bucket, checkpoint_key=config.checkpoint_key,
            local_path=local_ckpt, model=model, optimizer=optimizer,
        )
        resumed_from = epoch_start
        final_loss: float | None = None
        epochs_run = 0

        for epoch in range(epoch_start, config.epochs):
            total_loss = 0.0
            n_batches = 0
            for batch in make_batches():
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast(device_type=device_type, enabled=config.mixed_precision):
                    loss = train_step(model, batch)
                scaler.scale(loss).backward()
                if config.grad_clip is not None:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
                scaler.step(optimizer)
                scaler.update()
                total_loss += float(loss.detach())
                n_batches += 1

            final_loss = total_loss / n_batches if n_batches else None
            epochs_run += 1

            save_checkpoint(local_ckpt, model, optimizer, epoch)
            s3.upload_file(str(local_ckpt), results_bucket, config.checkpoint_key)

            loss_text = f"{final_loss:.4f}" if final_loss is not None else "n/a"
            event_repo.append(
                user_id, job_id, stage="Fine-tuning",
                message=f"epoch {epoch + 1}/{config.epochs}, loss={loss_text}",
            )
            control.check()

        return FineTuneResult(
            epochs_run=epochs_run, final_loss=final_loss, resumed_from_epoch=resumed_from
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


__all__ = [
    "BatchIterableFactory",
    "FineTuneConfig",
    "FineTuneResult",
    "TrainStepFn",
    "load_checkpoint",
    "run_finetune_loop",
    "save_checkpoint",
]
