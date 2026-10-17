"""Tests for availability.check_availability — server-side port of availability.ts."""

from __future__ import annotations

from modelforge_catalog import OPERATIONS, ModelInfo, check_availability
from modelforge_catalog.models import OperationSpec


def _op(**overrides: object) -> OperationSpec:
    base = dict(
        id="test_op",
        technique="quantization",
        label="Test op",
        description="",
        accuracy="lossless",
        typical_impact="",
        time_estimate="",
        source_formats=("onnx",),
    )
    base.update(overrides)
    return OperationSpec(**base)  # type: ignore[arg-type]


def _model(**overrides: object) -> ModelInfo:
    base = dict(format="onnx", family="vision", bits=32.0, params=1_000_000.0, size=4_000_000)
    base.update(overrides)
    return ModelInfo(**base)  # type: ignore[arg-type]


def test_gguf_model_is_never_available() -> None:
    result = check_availability(_op(), _model(format="gguf"))
    assert result.ok is False
    assert "GGUF" in (result.why or "")


def test_unsupported_source_format_is_unavailable() -> None:
    result = check_availability(_op(source_formats=("torch",)), _model(format="onnx"))
    assert result.ok is False
    assert "PyTorch" in (result.why or "")


def test_family_mismatch_for_llm_only_op() -> None:
    result = check_availability(_op(allowed_families=("llm",)), _model(family="vision"))
    assert result.ok is False
    assert "language model" in (result.why or "").lower()


def test_family_mismatch_for_non_llm_op() -> None:
    result = check_availability(_op(allowed_families=("vision",)), _model(family="llm"))
    assert result.ok is False
    assert "distillation" in (result.why or "").lower()


def test_already_at_or_below_required_bit_width_is_unavailable() -> None:
    result = check_availability(_op(required_bit_width=8), _model(bits=4.0))
    assert result.ok is False
    assert "4.0-bit" in (result.why or "")


def test_already_in_target_format_is_unavailable() -> None:
    result = check_availability(_op(target_format="onnx"), _model(format="onnx"))
    assert result.ok is False
    assert "already in this format" in (result.why or "")


def test_available_when_all_checks_pass() -> None:
    result = check_availability(_op(source_formats=("onnx",)), _model(format="onnx"))
    assert result.ok is True
    assert result.why is None


def test_real_catalog_operations_all_resolve_without_error() -> None:
    model = _model()
    for op in OPERATIONS:
        result = check_availability(op, model)
        assert isinstance(result.ok, bool)
