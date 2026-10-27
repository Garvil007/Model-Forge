"""Job-orchestration tests for `l_svd`: build a tiny real torch/safetensors weight
dict, run the real op end to end against fake S3/job/model/event repositories, and
check the reconstructed weight stays close to the original at high energy, that the
parameter count actually drops as predicted, and that the output file is smaller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from modelforge_db.records import ModelRecord

from ops import lowrank_svd
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository, model_record
from tests.test_prune_magnitude import _FakeJobRepository, _FakeModelRepository, _FakeS3


def _run_svd(
    model: ModelRecord, model_bytes: bytes, params: dict[str, Any]
) -> tuple[_FakeJobRepository, FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = FakeJobEventRepository()
    models = _FakeModelRepository(model)
    lowrank_svd.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params, operation=None,
        control=AlwaysOkControl(), event_repo=events, job_repo=jobs, models_repo=models,
        s3_client_override=s3,
    )
    return jobs, events, s3


def test_torch_svd_at_high_energy_keeps_output_close_and_shrinks_params(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    # Low effective rank so a thin factorization at 99% energy genuinely saves params:
    # out=64, in=64, true rank 8 -> full params 4096, rank-8 factors 8*(64+64)=1024.
    base = torch.randn(64, 8) @ torch.randn(8, 64)
    state_dict = {"mlp.weight": base, "mlp.bias": torch.randn(64)}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, events, s3 = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 99, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert any(e.stage == "Decomposing layers" for e in events.events)

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    factored = torch.load(output_path, map_location="cpu", weights_only=True)

    assert "mlp.weight" not in factored
    assert "mlp.weight__lowrank_u" in factored
    assert "mlp.weight__lowrank_v" in factored
    assert factored["mlp.bias"].shape == (64,)  # bias untouched

    u = factored["mlp.weight__lowrank_u"].numpy()
    v = factored["mlp.weight__lowrank_v"].numpy()
    reconstructed = u @ v
    relative_error = np.linalg.norm(reconstructed - base.numpy()) / np.linalg.norm(base.numpy())
    assert relative_error < 0.05  # outputs stay close at high energy

    params_before = 64 * 64
    params_after = u.size + v.size
    assert params_after < params_before  # parameter count drops as predicted

    assert output_path.stat().st_size < local_path.stat().st_size  # real file size drops


def test_safetensors_mode_fraction_reports_per_layer_rank(tmp_path: Path) -> None:
    pytest.importorskip("safetensors")
    from safetensors.numpy import load_file, save_file

    rng = np.random.default_rng(0)
    tensors = {"dense.weight": rng.standard_normal((40, 40)).astype(np.float32)}
    local_path = tmp_path / "model.safetensors"
    save_file(tensors, str(local_path))

    model = model_record(filename="model.safetensors", model_format="safetensors")
    jobs, _, s3 = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "fraction", "rank": 25, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert "dense.weight: rank 10" in metrics["Per-layer ranks"]  # 25% of rank-40

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.safetensors"
    output_path.write_bytes(output_bytes)
    factored = load_file(str(output_path))
    assert "dense.weight" not in factored
    assert factored["dense.weight__lowrank_u"].shape == (40, 10)
    assert factored["dense.weight__lowrank_v"].shape == (10, 40)


def test_attn_layer_skipped_when_layers_is_mlp(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    state_dict = {"self_attn.q_proj.weight": torch.randn(32, 32)}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _, s3 = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 50, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert jobs.calls[-1]["result"]["metrics"]["Layers factorized"].startswith("0 of 0")

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    unchanged = torch.load(output_path, map_location="cpu", weights_only=True)
    assert "self_attn.q_proj.weight" in unchanged  # left alone, not factorized


def test_finetune_requested_but_not_available_is_noted_not_failed(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    state_dict = {"mlp.weight": torch.randn(16, 16)}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _, _ = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 80, "layers": "mlp", "finetune": True},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert "skipped" in jobs.calls[-1]["result"]["metrics"]["Fine-tuning"]


def test_onnx_source_fails_cleanly_as_unsupported(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    import onnx
    from onnx import TensorProto, helper

    weight = helper.make_tensor(
        "w", TensorProto.FLOAT, [4, 4], list(np.zeros(16, dtype=np.float32))
    )
    node = helper.make_node("Identity", ["w"], ["out"])
    graph = helper.make_graph(
        [node], "g", [], [helper.make_tensor_value_info("out", TensorProto.FLOAT, [4, 4])],
        initializer=[weight],
    )
    model_proto = helper.make_model(graph)
    local_path = tmp_path / "model.onnx"
    onnx.save(model_proto, str(local_path))

    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _, _ = _run_svd(
        model, local_path.read_bytes(), {"mode": "energy", "energy": 95, "finetune": False}
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"
