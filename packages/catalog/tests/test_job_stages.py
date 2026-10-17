"""Tests for job_stages.stages_for_operation — must match apps/web/src/mocks/jobStages.ts."""

from __future__ import annotations

from modelforge_catalog import OPERATIONS, stages_for_operation


def _op(op_id: str):
    return next(o for o in OPERATIONS if o.id == op_id)


def test_quantization_without_calibration() -> None:
    labels = [s.label for s in stages_for_operation(_op("q_int8_dyn"), {})]
    assert labels == ["Loading model", "Quantizing weights", "Measuring accuracy"]


def test_quantization_with_calibration() -> None:
    labels = [s.label for s in stages_for_operation(_op("q_int8_static"), {})]
    assert labels == [
        "Loading model",
        "Running calibration data",
        "Quantizing weights",
        "Measuring accuracy",
    ]


def test_gguf_calibration_only_when_imatrix_set() -> None:
    op = _op("q_gguf")
    assert "Running calibration data" not in [s.label for s in stages_for_operation(op, {})]
    assert "Running calibration data" in [
        s.label for s in stages_for_operation(op, {"imatrix": True})
    ]


def test_pruning_without_finetune() -> None:
    labels = [s.label for s in stages_for_operation(_op("p_magnitude"), {})]
    assert labels == ["Loading model", "Scoring weights", "Pruning", "Measuring accuracy"]


def test_pruning_with_finetune_inserts_epoch_stage() -> None:
    stages = stages_for_operation(_op("p_magnitude"), {"finetune": True, "epochs": 5})
    assert [s.label for s in stages] == [
        "Loading model",
        "Scoring weights",
        "Pruning",
        "Fine-tuning",
        "Measuring accuracy",
    ]
    finetune_stage = next(s for s in stages if s.label == "Fine-tuning")
    assert finetune_stage.epochs == 5


def test_distillation_has_training_epochs() -> None:
    stages = stages_for_operation(_op("d_logit"), {"epochs": 20})
    labels = [s.label for s in stages]
    assert labels == [
        "Loading teacher",
        "Building student",
        "Training student",
        "Measuring accuracy",
    ]
    training = next(s for s in stages if s.label == "Training student")
    assert training.epochs == 20


def test_distillation_default_epochs() -> None:
    training = next(
        s for s in stages_for_operation(_op("d_logit"), {}) if s.label == "Training student"
    )
    assert training.epochs == 12


def test_lowrank_without_finetune() -> None:
    labels = [s.label for s in stages_for_operation(_op("l_svd"), {})]
    assert labels == ["Loading model", "Decomposing layers", "Measuring accuracy"]


def test_convert_stage_names_target() -> None:
    op = _op("c_onnx")
    labels = [s.label for s in stages_for_operation(op, {})]
    assert labels == ["Loading model", f"Converting to {op.label}", "Checking outputs match"]
