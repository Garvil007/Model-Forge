"""Job-orchestration test for `p_24` — builds a tiny torch state_dict with a weight
tensor whose last dim is a multiple of 4, runs the real op, and checks the result has
exactly 2 zeros in every contiguous group of 4 along that axis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from modelforge_db.records import ModelRecord

from ops import prune_24
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository, model_record
from tests.test_prune_magnitude import _FakeJobRepository, _FakeModelRepository, _FakeS3


def _run_prune(
    model: ModelRecord, model_bytes: bytes, params: dict[str, Any]
) -> tuple[_FakeJobRepository, FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = FakeJobEventRepository()
    models = _FakeModelRepository(model)
    prune_24.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params, operation=None,
        control=AlwaysOkControl(), event_repo=events, job_repo=jobs, models_repo=models,
        s3_client_override=s3,
    )
    return jobs, events, s3


def test_torch_24_pattern_zeroes_exactly_half_of_every_group_of_four(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    state_dict = {"layer.weight": torch.randn(8, 16)}  # last dim 16 is a multiple of 4
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _, s3 = _run_prune(model, local_path.read_bytes(), {"finetune": False})

    assert jobs.calls[-1]["status"] == "succeeded"
    assert jobs.calls[-1]["result"]["speedNote"] == "about 1.4 times faster on Ampere+ GPUs"

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    pruned_state_dict = torch.load(output_path, map_location="cpu", weights_only=True)
    weight = pruned_state_dict["layer.weight"]
    groups = weight.reshape(8, 4, 4)
    zero_counts_per_group = (groups == 0).sum(dim=-1)
    assert torch.all(zero_counts_per_group == 2)
