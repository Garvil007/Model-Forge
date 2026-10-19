"""Tests for specific OperationSpec entries in methods.py."""

from __future__ import annotations

from modelforge_catalog import METHODS


def _method(op_id: str):
    return next(m for m in METHODS if m.id == op_id)


def test_q_int8_static_runs_on_the_torch_worker_image() -> None:
    # Bug fix: q_int8_static was missing worker_image, unlike its sibling q_int8_dyn which
    # already declares worker_image="cpu-torch".
    op = _method("q_int8_static")
    assert op.worker_image == "cpu-torch"


def test_q_int8_static_calib_param_help_mentions_dataset_id() -> None:
    op = _method("q_int8_static")
    calib = next(p for p in op.params if p.name == "calib")
    assert calib.type == "dataset"
    assert "dataset" in calib.help.lower()
