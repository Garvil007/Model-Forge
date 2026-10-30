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


def test_onnx_gemm_rewrite_runs_through_onnxruntime_close_to_original(tmp_path: Path) -> None:
    onnx = pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    # Low effective rank (true rank 6) so 99% energy genuinely saves params and the
    # rewritten graph reconstructs close to the pre-factorization Gemm output.
    base = (rng.standard_normal((32, 6)) @ rng.standard_normal((6, 32))).astype(np.float32)
    bias = rng.standard_normal(32).astype(np.float32)

    weight_init = numpy_helper.from_array(base, "mlp.weight")
    bias_init = numpy_helper.from_array(bias, "mlp.bias")
    node = helper.make_node(
        "Gemm", ["x", "mlp.weight", "mlp.bias"], ["y"], transB=1, name="mlp_gemm"
    )
    graph = helper.make_graph(
        [node], "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 32])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 32])],
        initializer=[weight_init, bias_init],
    )
    model_proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model_proto.ir_version = 9  # pin below onnxruntime's max supported IR in this sandbox
    local_path = tmp_path / "model.onnx"
    onnx.save(model_proto, str(local_path))

    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _, s3 = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 99, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    metrics = jobs.calls[-1]["result"]["metrics"]
    assert "1 of 1" in metrics["Layers factorized"]

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.onnx"
    output_path.write_bytes(output_bytes)
    assert output_path.stat().st_size < local_path.stat().st_size

    session = ort.InferenceSession(str(output_path))
    x = rng.standard_normal((1, 32)).astype(np.float32)
    (y,) = session.run(None, {"x": x})
    expected = x @ base.T + bias
    relative_error = np.linalg.norm(y - expected) / np.linalg.norm(expected)
    assert relative_error < 0.05  # outputs stay close: true rank 6 well under the chosen rank


def test_onnx_shared_weight_is_left_untouched(tmp_path: Path) -> None:
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    weight = rng.standard_normal((16, 16)).astype(np.float32)
    weight_init = numpy_helper.from_array(weight, "shared.weight")
    node_a = helper.make_node("Gemm", ["x", "shared.weight"], ["y1"], transB=1, name="a")
    node_b = helper.make_node("Gemm", ["x", "shared.weight"], ["y2"], transB=1, name="b")
    graph = helper.make_graph(
        [node_a, node_b], "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 16])],
        [
            helper.make_tensor_value_info("y1", TensorProto.FLOAT, [1, 16]),
            helper.make_tensor_value_info("y2", TensorProto.FLOAT, [1, 16]),
        ],
        initializer=[weight_init],
    )
    model_proto = helper.make_model(graph)
    local_path = tmp_path / "model.onnx"
    onnx.save(model_proto, str(local_path))

    model = model_record(filename="model.onnx", model_format="onnx")
    jobs, _, _ = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 50, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert jobs.calls[-1]["result"]["metrics"]["Layers factorized"].startswith("0 of 0")


def test_keras_sequential_svd_rebuilds_a_real_runnable_model(tmp_path: Path) -> None:
    tf = pytest.importorskip("tensorflow")

    keras_model = tf.keras.Sequential([tf.keras.layers.Dense(32, input_shape=(32,))])
    local_path = tmp_path / "model.h5"
    keras_model.save(str(local_path))

    model = model_record(filename="model.h5", model_format="keras")
    jobs, events, s3 = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 80, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert any(e.stage == "Decomposing layers" for e in events.events)

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "output.h5"
    output_path.write_bytes(output_bytes)
    rebuilt = tf.keras.models.load_model(str(output_path), compile=False, safe_mode=True)

    dense_layers = [layer for layer in rebuilt.layers if isinstance(layer, tf.keras.layers.Dense)]
    assert len(dense_layers) == 2  # one Dense split into two smaller ones

    x = np.random.default_rng(0).standard_normal((1, 32)).astype(np.float32)
    y = rebuilt.predict(x, verbose=0)
    assert y.shape == (1, 32)


def test_keras_functional_non_sequential_svd_fails_cleanly_as_unsupported(
    tmp_path: Path,
) -> None:
    tf = pytest.importorskip("tensorflow")

    inputs = tf.keras.Input(shape=(16,))
    branch_a = tf.keras.layers.Dense(16)(inputs)
    branch_b = tf.keras.layers.Dense(16)(inputs)
    outputs = tf.keras.layers.Add()([branch_a, branch_b])
    keras_model = tf.keras.Model(inputs, outputs)
    local_path = tmp_path / "model.h5"
    keras_model.save(str(local_path))

    model = model_record(filename="model.h5", model_format="keras")
    jobs, _, _ = _run_svd(
        model, local_path.read_bytes(),
        {"mode": "energy", "energy": 80, "layers": "mlp", "finetune": False},
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"
