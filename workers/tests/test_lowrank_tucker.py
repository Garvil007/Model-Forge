"""Job-orchestration tests for `l_tucker`: build a tiny real torch Conv2d weight
tensor, run the real op end to end against fake S3/job/model/event repositories, and
check both the Tucker-2 and CP paths keep the reconstruction close, drop the parameter
count, and shrink the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from modelforge_db.records import ModelRecord

from ops import lowrank_tucker
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository, model_record
from tests.test_prune_magnitude import _FakeJobRepository, _FakeModelRepository, _FakeS3


def _run_tucker(
    model: ModelRecord, model_bytes: bytes, params: dict[str, Any]
) -> tuple[_FakeJobRepository, FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = FakeJobEventRepository()
    models = _FakeModelRepository(model)
    lowrank_tucker.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params, operation=None,
        control=AlwaysOkControl(), event_repo=events, job_repo=jobs, models_repo=models,
        s3_client_override=s3,
    )
    return jobs, events, s3


def _low_rank_conv_kernel(out_ch: int, in_ch: int, kh: int, kw: int, true_rank: int) -> np.ndarray:
    """A Tucker-2-structured kernel (true channel rank `true_rank`, full spatial
    modes) via tensorly's own `tucker_to_tensor`, so a generous requested rank can
    reconstruct it almost exactly — the same "deliberately low-rank" trick
    `test_lowrank_svd.py` uses for its matrix case."""
    import tensorly as tl

    rng = np.random.default_rng(0)
    core = rng.standard_normal((true_rank, true_rank, kh, kw))
    factor_out = rng.standard_normal((out_ch, true_rank))
    factor_in = rng.standard_normal((in_ch, true_rank))
    return tl.tenalg.multi_mode_dot(core, [factor_out, factor_in], modes=[0, 1])


def test_torch_tucker2_keeps_reconstruction_close_and_shrinks_params(tmp_path: Path) -> None:
    pytest.importorskip("tensorly")
    torch = pytest.importorskip("torch")

    kernel_np = _low_rank_conv_kernel(32, 32, 3, 3, true_rank=6)
    kernel = torch.from_numpy(kernel_np).float()
    state_dict = {"conv1.weight": kernel}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, events, s3 = _run_tucker(
        model, local_path.read_bytes(), {"kind": "tucker2", "rank": 50, "finetune": False}
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert any(e.stage == "Decomposing layers" for e in events.events)

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    factored = torch.load(output_path, map_location="cpu", weights_only=True)

    assert "conv1.weight" not in factored
    core = factored["conv1.weight__tucker_core"].numpy()
    factor_out = factored["conv1.weight__tucker_factor_out"].numpy()
    factor_in = factored["conv1.weight__tucker_factor_in"].numpy()

    reconstructed = np.einsum("or,ic,rcxy->oixy", factor_out, factor_in, core)
    relative_error = np.linalg.norm(reconstructed - kernel_np) / np.linalg.norm(kernel_np)
    assert relative_error < 0.1  # outputs stay close: true rank 6 well under the chosen 16

    params_before = 32 * 32 * 3 * 3
    params_after = core.size + factor_out.size + factor_in.size
    assert params_after < params_before
    assert output_path.stat().st_size < local_path.stat().st_size


def _low_rank_cp_conv_kernel(
    out_ch: int, in_ch: int, kh: int, kw: int, true_rank: int
) -> np.ndarray:
    """A CP-structured kernel (true rank `true_rank`) via tensorly's `cp_to_tensor`, so
    a generous requested rank can reconstruct it almost exactly."""
    import tensorly as tl

    rng = np.random.default_rng(1)
    factors = [
        rng.standard_normal((out_ch, true_rank)), rng.standard_normal((in_ch, true_rank)),
        rng.standard_normal((kh, true_rank)), rng.standard_normal((kw, true_rank)),
    ]
    weights = np.ones(true_rank)
    return tl.cp_to_tensor((weights, factors))


def test_torch_cp_decomposition_keeps_reconstruction_close_and_shrinks_params(
    tmp_path: Path,
) -> None:
    pytest.importorskip("tensorly")
    torch = pytest.importorskip("torch")

    kernel_np = _low_rank_cp_conv_kernel(16, 16, 3, 3, true_rank=3)
    kernel = torch.from_numpy(kernel_np).float()
    state_dict = {"conv1.weight": kernel}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _, s3 = _run_tucker(
        model, local_path.read_bytes(), {"kind": "cp", "rank": 50, "finetune": False}
    )

    assert jobs.calls[-1]["status"] == "succeeded"

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    factored = torch.load(output_path, map_location="cpu", weights_only=True)

    assert "conv1.weight" not in factored
    weights = factored["conv1.weight__cp_weights"].numpy()
    factor_out = factored["conv1.weight__cp_factor_out"].numpy()
    factor_in = factored["conv1.weight__cp_factor_in"].numpy()
    factor_kh = factored["conv1.weight__cp_factor_kh"].numpy()
    factor_kw = factored["conv1.weight__cp_factor_kw"].numpy()

    reconstructed = np.einsum(
        "r,or,ir,xr,yr->oixy", weights, factor_out, factor_in, factor_kh, factor_kw
    )
    relative_error = np.linalg.norm(reconstructed - kernel_np) / np.linalg.norm(kernel_np)
    assert relative_error < 0.1  # outputs stay close: true rank 3 well under the chosen 8

    params_before = 16 * 16 * 3 * 3
    params_after = (
        weights.size + factor_out.size + factor_in.size + factor_kh.size + factor_kw.size
    )
    assert params_after < params_before
    assert output_path.stat().st_size < local_path.stat().st_size


def test_small_rank_layer_skipped_when_no_param_saving(tmp_path: Path) -> None:
    pytest.importorskip("tensorly")
    torch = pytest.importorskip("torch")

    torch.manual_seed(0)
    # Tiny 4x4x1x1 kernel: even a generous rank can't beat 16 raw params once factor
    # overhead is counted, so this layer should be left untouched.
    kernel = torch.randn(4, 4, 1, 1)
    state_dict = {"conv1.weight": kernel}
    local_path = tmp_path / "model.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _, s3 = _run_tucker(
        model, local_path.read_bytes(), {"kind": "tucker2", "rank": 75, "finetune": False}
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert jobs.calls[-1]["result"]["metrics"]["Layers factorized"].startswith("0 of 1")

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.pt"
    output_path.write_bytes(output_bytes)
    unchanged = torch.load(output_path, map_location="cpu", weights_only=True)
    assert "conv1.weight" in unchanged


def test_keras_source_fails_cleanly_as_unsupported(tmp_path: Path) -> None:
    pytest.importorskip("tensorflow")
    import tensorflow as tf

    keras_model = tf.keras.Sequential(
        [tf.keras.layers.Conv2D(4, 3, input_shape=(8, 8, 4))]
    )
    local_path = tmp_path / "model.h5"
    keras_model.save(str(local_path))

    model = model_record(filename="model.h5", model_format="keras")
    jobs, _, _ = _run_tucker(
        model, local_path.read_bytes(), {"kind": "tucker2", "rank": 30, "finetune": False}
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"
