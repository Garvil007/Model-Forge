"""Unit tests for `d_llm`'s student-construction logic. A full HF-download +
train + measure integration test isn't written here, matching this repo's existing
choice not to integration-test the other GPU-only LLM ops (`p_wanda`, `q_gptq`,
`q_awq`, `q_nf4` have no `test_*.py` of their own either — only the shared runner
plumbing they call, `_llm_gpu_common.py`, is covered end to end in
`test_llm_gpu_common.py`). This file instead proves `_build_layerdrop_student` does a
real, structural layer drop on a tiny in-process model, with no network and no HF
download involved.
"""

from __future__ import annotations

import pytest

from ops import distill_llm


def _tiny_llama(num_hidden_layers: int = 4):
    from transformers import LlamaConfig, LlamaForCausalLM

    config = LlamaConfig(
        vocab_size=32, hidden_size=8, intermediate_size=16,
        num_hidden_layers=num_hidden_layers, num_attention_heads=2, num_key_value_heads=2,
        max_position_embeddings=64,
    )
    model = LlamaForCausalLM(config)
    model.eval()
    return model


def test_layerdrop_keeps_every_other_decoder_layer() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    teacher = _tiny_llama(num_hidden_layers=4)
    student = distill_llm._build_layerdrop_student(teacher)

    assert len(student.model.layers) == 2  # every other of 4 kept
    assert student.config.num_hidden_layers == 2
    assert len(teacher.model.layers) == 4  # teacher itself is untouched

    student_params = sum(p.numel() for p in student.parameters())
    teacher_params = sum(p.numel() for p in teacher.parameters())
    assert student_params < teacher_params  # a real, measurable size drop


def test_small_student_option_is_refused_cleanly() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    teacher = _tiny_llama(num_hidden_layers=2)
    with pytest.raises(distill_llm.UnsupportedFormatError):
        distill_llm._build_student(teacher, {"student": "small"})
