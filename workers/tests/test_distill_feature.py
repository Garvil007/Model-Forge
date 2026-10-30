"""Job-orchestration tests for `d_feature` (feature-based distillation): a YOLO teacher
(a genuine eager `nn.Module` graph) exercises the real feature-matching hook path end
to end; ONNX and TorchScript teachers exercise the documented clean fallback to
response-only distillation (Python forward hooks don't fire on traced/scripted
submodules — see `_distill_common._TorchScriptTeacherAdapter`'s docstring).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from modelforge_db.records import ModelRecord

from ops import distill_feature
from tests._convert_fakes import AlwaysOkControl, FakeJobEventRepository, model_record
from tests.test_distill_response import _tiny_onnx_classifier
from tests.test_prune_magnitude import _FakeJobRepository, _FakeModelRepository, _FakeS3


def _run_distill(
    model: ModelRecord, model_bytes: bytes, params: dict[str, Any]
) -> tuple[_FakeJobRepository, FakeJobEventRepository, _FakeS3]:
    s3 = _FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = _FakeJobRepository()
    events = FakeJobEventRepository()
    models = _FakeModelRepository(model)
    distill_feature.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params, operation=None,
        control=AlwaysOkControl(), event_repo=events, job_repo=jobs, models_repo=models,
        s3_client_override=s3,
    )
    return jobs, events, s3


def _tiny_torchscript_classifier(tmp_path: Path) -> Path:
    import torch
    from torch import nn

    torch.manual_seed(0)
    teacher = nn.Sequential(
        nn.AdaptiveAvgPool2d(4), nn.Flatten(), nn.Linear(3 * 4 * 4, 5)
    )
    teacher.eval()
    scripted = torch.jit.trace(teacher, torch.randn(1, 3, 224, 224))
    local_path = tmp_path / "teacher.pt"
    scripted.save(str(local_path))
    return local_path


def test_torchscript_teacher_falls_back_to_response_only_with_a_note(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    local_path = _tiny_torchscript_classifier(tmp_path)
    model = model_record(filename="teacher.pt", model_format="torchscript")
    jobs, events, s3 = _run_distill(
        model, local_path.read_bytes(), {"student": "compact", "layers": "stages", "epochs": 1}
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert "traceable PyTorch/TorchScript/YOLO" in result["metrics"]["Feature matching"]
    training_events = [e for e in events.events if e.stage == "Training student"]
    assert len(training_events) == 1

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "student.pt"
    output_path.write_bytes(output_bytes)
    saved = torch.load(output_path, map_location="cpu", weights_only=False)
    assert sum(p.numel() for p in saved["model"].parameters()) > 0


def test_yolo_teacher_matches_a_real_intermediate_feature(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("ultralytics")
    import torch
    from ultralytics import YOLO

    yolo = YOLO("yolov8n.yaml")  # built from the architecture config, no weight download
    local_path = tmp_path / "teacher.pt"
    yolo.save(str(local_path))

    model = model_record(filename="teacher.pt", model_format="yolo")
    jobs, events, s3 = _run_distill(
        model, local_path.read_bytes(), {"student": "compact", "layers": "stages", "epochs": 1}
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert "Feature matching" not in result["metrics"]  # real hook engaged, no fallback note
    training_events = [e for e in events.events if e.stage == "Training student"]
    assert len(training_events) == 1

    output_bytes = next(iter(s3.uploaded.values()))
    output_path = tmp_path / "student.pt"
    output_path.write_bytes(output_bytes)
    saved = torch.load(output_path, map_location="cpu", weights_only=False)
    assert sum(p.numel() for p in saved["model"].parameters()) > 0


def test_onnx_teacher_falls_back_to_response_only_with_a_note(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    pytest.importorskip("torch")

    local_path = _tiny_onnx_classifier(tmp_path)
    model = model_record(filename="teacher.onnx", model_format="onnx")
    jobs, _, _ = _run_distill(
        model, local_path.read_bytes(), {"student": "compact", "layers": "last", "epochs": 1}
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    assert "response-only" in jobs.calls[-1]["result"]["metrics"]["Feature matching"]
