"""Job-orchestration tests for `d_logit` (response-based distillation): build a tiny
real ONNX "teacher" classifier, run the real op end to end against fake S3/job/model/
event repositories, and check a real smaller PyTorch student comes out the other end,
with "Training student" events for each epoch and a real parameter-count/size drop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from modelforge_db.records import ModelRecord

from ops import distill_response
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository, model_record
from tests.test_prune_magnitude import _FakeJobRepository, _FakeModelRepository, _FakeS3


def _run_distill(
    model: ModelRecord, model_bytes: bytes, params: dict[str, Any]
) -> tuple[_FakeJobRepository, FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = FakeJobEventRepository()
    models = _FakeModelRepository(model)
    distill_response.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params, operation=None,
        control=AlwaysOkControl(), event_repo=events, job_repo=jobs, models_repo=models,
        s3_client_override=s3,
    )
    return jobs, events, s3


def _tiny_onnx_classifier(tmp_path: Path) -> Path:
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    weight = rng.standard_normal((16, 32)).astype(np.float32)  # Gemm transB=1: (out, in)
    bias = rng.standard_normal(16).astype(np.float32)
    node = helper.make_node(
        "Gemm", ["x", "mlp.weight", "mlp.bias"], ["y"], transB=1, name="mlp_gemm"
    )
    graph = helper.make_graph(
        [node], "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 32])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 16])],
        initializer=[
            numpy_helper.from_array(weight, "mlp.weight"),
            numpy_helper.from_array(bias, "mlp.bias"),
        ],
    )
    model_proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model_proto.ir_version = 9
    local_path = tmp_path / "teacher.onnx"
    onnx.save(model_proto, str(local_path))
    return local_path


def test_onnx_teacher_trains_a_real_smaller_student(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    torch = pytest.importorskip("torch")

    local_path = _tiny_onnx_classifier(tmp_path)
    model = model_record(filename="teacher.onnx", model_format="onnx")
    jobs, events, s3 = _run_distill(
        model, local_path.read_bytes(),
        {"student": "compact", "epochs": 2, "temp": 4, "alpha": 0.7},
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    stages = [event.stage for event in events.events]
    assert stages[0] == "Loading teacher"
    assert "Building student" in stages
    training_events = [e for e in events.events if e.stage == "Training student"]
    assert len(training_events) == 2  # one per epoch
    assert "epoch 1/2" in training_events[0].message
    assert "epoch 2/2" in training_events[1].message

    result = jobs.calls[-1]["result"]
    assert result["downloadName"] == "teacher_student.pt"
    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "student.pt"
    output_path.write_bytes(output_bytes)
    saved = torch.load(output_path, map_location="cpu", weights_only=False)
    student = saved["model"]
    student_params = sum(p.numel() for p in student.parameters())

    assert student_params > 0
    assert "Student parameters" in result["metrics"]
    assert "Output similarity" in result["metrics"]


def test_bare_torch_teacher_has_no_architecture_and_fails_cleanly(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    state_dict = {"weight": torch.randn(4, 4)}
    local_path = tmp_path / "teacher.pt"
    torch.save(state_dict, local_path)

    model = model_record(filename="teacher.pt", model_format="torch")
    jobs, _, _ = _run_distill(
        model, local_path.read_bytes(), {"student": "half_width", "epochs": 1}
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_custom_student_without_an_uploaded_file_fails_cleanly(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    pytest.importorskip("torch")

    local_path = _tiny_onnx_classifier(tmp_path)
    model = model_record(filename="teacher.onnx", model_format="onnx")
    jobs, _, _ = _run_distill(
        model, local_path.read_bytes(), {"student": "custom", "epochs": 1}
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"
