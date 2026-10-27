"""Proves `workers/core/train.py::run_finetune_loop`'s checkpoint/resume contract —
Day 15's "fine-tuning run resumes after killing the worker" criterion — without needing
a real pruning op, a GPU, or Docker: a tiny `nn.Linear` + SGD stands in for whatever
model a real op would fine-tune, and a fake S3 (dict-backed, same shape as
`workers/tests/_convert_fakes.py::FakeS3` but with `download_file` reading the same
store `upload_file` writes to, so a checkpoint survives between two separate
`run_finetune_loop` calls the way it would between two separate worker processes).
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from core import train  # noqa: E402
from core.exceptions import SpotInterruptedError  # noqa: E402
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository  # noqa: E402

_RESULTS_BUCKET = "mf-results"
_CHECKPOINT_KEY = "users/user-1/jobs/job-1/checkpoint.pt"


class _FakeS3:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        data = self.store[(bucket, key)]  # KeyError => "no checkpoint yet", like real S3 404
        with open(local_path, "wb") as fh:
            fh.write(data)

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        with open(local_path, "rb") as fh:
            self.store[(bucket, key)] = fh.read()


class _InterruptAfterNCalls:
    """Raises `SpotInterruptedError` on the Nth `.check()` call, then behaves like
    `AlwaysOkControl` forever after — simulating a worker killed mid-fine-tune once."""

    def __init__(self, raise_on_call: int) -> None:
        self._raise_on_call = raise_on_call
        self._calls = 0

    def check(self) -> None:
        self._calls += 1
        if self._calls == self._raise_on_call:
            raise SpotInterruptedError("simulated spot interruption")


def _make_model_and_optimizer() -> tuple[torch.nn.Module, torch.optim.Optimizer]:
    torch.manual_seed(0)
    model = torch.nn.Linear(4, 2)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    return model, optimizer


def _batches() -> list[tuple[torch.Tensor, torch.Tensor]]:
    x = torch.randn(8, 4)
    y = torch.randn(8, 2)
    return [(x, y)]


def _train_step(model: torch.nn.Module, batch: tuple[torch.Tensor, torch.Tensor]) -> torch.Tensor:
    x, y = batch
    return torch.nn.functional.mse_loss(model(x), y)


def test_runs_all_epochs_and_checkpoints_each_one() -> None:
    model, optimizer = _make_model_and_optimizer()
    s3 = _FakeS3()
    events = FakeJobEventRepository()
    config = train.FineTuneConfig(epochs=3, checkpoint_key=_CHECKPOINT_KEY, mixed_precision=False)

    result = train.run_finetune_loop(
        model=model, optimizer=optimizer, make_batches=_batches, train_step=_train_step,
        config=config, user_id="user-1", job_id="job-1", event_repo=events,
        control=AlwaysOkControl(), s3=s3, results_bucket=_RESULTS_BUCKET, device="cpu",
    )

    assert result.epochs_run == 3
    assert result.resumed_from_epoch == 0
    assert (_RESULTS_BUCKET, _CHECKPOINT_KEY) in s3.store
    assert [e.stage for e in events.events] == ["Fine-tuning"] * 3
    epoch_labels = [e.message.split(",")[0] for e in events.events]
    assert epoch_labels == ["epoch 1/3", "epoch 2/3", "epoch 3/3"]


def test_resumes_from_the_next_epoch_after_a_simulated_worker_kill() -> None:
    config = train.FineTuneConfig(epochs=3, checkpoint_key=_CHECKPOINT_KEY, mixed_precision=False)
    s3 = _FakeS3()
    events_first_attempt = FakeJobEventRepository()
    model, optimizer = _make_model_and_optimizer()

    # First attempt: interrupted right after epoch 0 finishes (its checkpoint is saved
    # and its event emitted before control.check() raises).
    with pytest.raises(SpotInterruptedError):
        train.run_finetune_loop(
            model=model, optimizer=optimizer, make_batches=_batches, train_step=_train_step,
            config=config, user_id="user-1", job_id="job-1", event_repo=events_first_attempt,
            control=_InterruptAfterNCalls(raise_on_call=1), s3=s3, results_bucket=_RESULTS_BUCKET,
            device="cpu",
        )
    assert [e.message.split(",")[0] for e in events_first_attempt.events] == ["epoch 1/3"]
    assert (_RESULTS_BUCKET, _CHECKPOINT_KEY) in s3.store

    # Second attempt: a fresh model/optimizer (as a real worker restart would build),
    # same job_id, same fake S3 — must resume at epoch index 1, not epoch 0.
    resumed_model, resumed_optimizer = _make_model_and_optimizer()
    events_second_attempt = FakeJobEventRepository()
    result = train.run_finetune_loop(
        model=resumed_model, optimizer=resumed_optimizer, make_batches=_batches,
        train_step=_train_step, config=config, user_id="user-1", job_id="job-1",
        event_repo=events_second_attempt, control=AlwaysOkControl(), s3=s3,
        results_bucket=_RESULTS_BUCKET, device="cpu",
    )

    assert result.resumed_from_epoch == 1
    assert result.epochs_run == 2
    assert [e.message.split(",")[0] for e in events_second_attempt.events] == [
        "epoch 2/3", "epoch 3/3",
    ]


def test_checkpoint_round_trips_model_and_optimizer_state(tmp_path: object) -> None:
    import pathlib

    model, optimizer = _make_model_and_optimizer()
    for batch in _batches():
        optimizer.zero_grad()
        _train_step(model, batch).backward()
        optimizer.step()
    checkpoint_path = pathlib.Path(str(tmp_path)) / "checkpoint.pt"
    train.save_checkpoint(checkpoint_path, model, optimizer, completed_epoch=4)

    restored_model, restored_optimizer = _make_model_and_optimizer()
    next_epoch = train.load_checkpoint(checkpoint_path, restored_model, restored_optimizer)

    assert next_epoch == 5
    for original, restored in zip(model.parameters(), restored_model.parameters(), strict=True):
        assert torch.equal(original, restored)
