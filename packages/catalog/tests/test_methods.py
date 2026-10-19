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


def test_q_gguf_runs_on_the_cpu_llm_worker_image() -> None:
    # GGUF quantization is llama.cpp CPU work, not GPU — cheaper and fast enough, so it
    # must not inherit the gpu-base image/queue the way q_gptq/q_awq do.
    op = _method("q_gguf")
    assert op.worker_image == "cpu-llm"
    assert op.queue == "cpu"


def test_q_nf4_runs_on_the_gpu_worker_image() -> None:
    # Bug fix: q_nf4 (bitsandbytes) was missing worker_image/queue entirely, unlike its
    # sibling q_gptq/q_awq which already declare worker_image="gpu-base", queue="gpu".
    op = _method("q_nf4")
    assert op.worker_image == "gpu-base"
    assert op.queue == "gpu"
