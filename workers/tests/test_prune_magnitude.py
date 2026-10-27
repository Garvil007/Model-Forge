"""Full job-orchestration tests for `p_magnitude`, same shape as
`workers/tests/_convert_fakes.py`'s convert-op tests: build a tiny real model per
format, run the real op end to end against fake S3/job/model/event repositories, then
load the real pruned output back through the real runtime and check it's actually
sparser than the input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from modelforge_db.records import ModelRecord

from ops import prune_magnitude
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository, model_record


class _FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects
        self.uploaded: dict[tuple[str, str], bytes] = {}

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        with open(local_path, "wb") as fh:
            fh.write(self.objects[(bucket, key)])

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        with open(local_path, "rb") as fh:
            self.uploaded[(bucket, key)] = fh.read()


class _FakeJobRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_progress(
        self, user_id: str, job_id: str, *, status: str, progress_percent: int,
        result: dict[str, Any] | None = None, error: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append({"status": status, "result": result, "error": error})


class _FakeModelRepository:
    def __init__(self, record: ModelRecord) -> None:
        self.record = record

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        return self.record


def _run_prune(
    model: ModelRecord, model_bytes: bytes, params: dict[str, Any]
) -> tuple[_FakeJobRepository, FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = FakeJobEventRepository()
    models = _FakeModelRepository(model)
    prune_magnitude.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params, operation=None,
        control=AlwaysOkControl(), event_repo=events, job_repo=jobs, models_repo=models,
        s3_client_override=s3,
    )
    return jobs, events, s3


def test_torch_global_magnitude_pruning_increases_sparsity(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    state_dict = {"layer.weight": torch.randn(32, 32), "layer.bias": torch.randn(32)}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, events, s3 = _run_prune(
        model, local_path.read_bytes(),
        {"sparsity": 50, "scope": "global", "storage": "dense", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert any(e.stage == "Pruning" for e in events.events)
    assert any(e.stage == "Scoring weights" for e in events.events)

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    pruned_state_dict = torch.load(output_path, map_location="cpu", weights_only=True)
    zero_fraction = float((pruned_state_dict["layer.weight"] == 0).float().mean())
    assert zero_fraction >= 0.45  # ~50% target sparsity on the prunable weight tensor
    assert float((pruned_state_dict["layer.bias"] == 0).float().mean()) < 0.5  # bias untouched


def test_torch_sparse_storage_uses_real_sparse_tensors(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    state_dict = {"layer.weight": torch.randn(16, 16)}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    _, _, s3 = _run_prune(
        model, local_path.read_bytes(),
        {"sparsity": 70, "scope": "global", "storage": "sparse", "finetune": False},
    )

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    pruned = torch.load(output_path, map_location="cpu", weights_only=False)
    assert pruned["layer.weight"].is_sparse


def test_safetensors_per_layer_pruning(tmp_path: Path) -> None:
    pytest.importorskip("safetensors")
    from safetensors.numpy import load_file, save_file

    rng = np.random.default_rng(0)
    tensors = {"weight": rng.standard_normal((20, 20)).astype(np.float32)}
    local_path = tmp_path / "model.safetensors"
    save_file(tensors, str(local_path))

    model = model_record(filename="model.safetensors", model_format="safetensors")
    jobs, _, s3 = _run_prune(
        model, local_path.read_bytes(),
        {"sparsity": 60, "scope": "layer", "storage": "dense", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.safetensors"
    output_path.write_bytes(output_bytes)
    pruned = load_file(str(output_path))
    zero_fraction = float((pruned["weight"] == 0).mean())
    assert zero_fraction >= 0.55


def test_finetune_requested_but_not_available_is_noted_not_failed(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    state_dict = {"layer.weight": torch.randn(8, 8)}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _, _ = _run_prune(
        model, local_path.read_bytes(),
        {"sparsity": 50, "scope": "global", "storage": "dense", "finetune": True},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert "skipped" in jobs.calls[-1]["result"]["metrics"]["Fine-tuning"]
