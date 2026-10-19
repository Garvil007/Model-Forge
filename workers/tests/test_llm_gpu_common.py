"""CPU test mode for the GPU-LLM quantization runner (`_llm_gpu_common.run_llm_gpu_quantize`,
shared by q_gptq/q_awq/q_nf4): a tiny random `LlamaConfig`/`LlamaForCausalLM`, no network,
no GPU — `MF_LLM_DEVICE` set to "cpu" and `huggingface_hub.snapshot_download` monkeypatched
to copy a locally-saved checkpoint instead of hitting the real Hub. Exercises the real
`core.evaluators.perplexity.PerplexityEvaluator` (via `_HfCausalLmRunner`) against a real
forward pass, not a mocked perplexity number — only the quantization step itself
(`quantize_fn`) is swapped for a fake, since that's each op's own thin wrapper around
llm-compressor/bitsandbytes (covered, where installed, by `test_quantize_nf4.py` etc).

Skipped in any environment without `torch`/`transformers` installed (not part of this
sandbox's base install — see `docs/PROGRESS.md`'s Day 14 entry) rather than faking a pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from ops import _llm_gpu_common as llm_gpu_common  # noqa: E402
from tests._convert_fakes import (  # noqa: E402
    AlwaysOkControl,
    FakeJobEventRepository,
    FakeJobRepository,
    FakeModelRepository,
    FakeS3,
    model_record,
)

_VOCAB_SIZE = 64


def _tiny_llama_repo(tmp_path: Path) -> Path:
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast

    config = LlamaConfig(
        vocab_size=_VOCAB_SIZE, hidden_size=16, intermediate_size=32,
        num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2,
        max_position_embeddings=128,
    )
    model = LlamaForCausalLM(config)
    model.eval()

    vocab = {f"tok{i}": i for i in range(_VOCAB_SIZE)}
    tokenizer_backend = Tokenizer(WordLevel(vocab=vocab, unk_token="tok0"))
    tokenizer_backend.pre_tokenizer = Whitespace()
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=tokenizer_backend)
    tokenizer.pad_token = "tok0"

    repo_dir = tmp_path / "tiny_llama_repo"
    model.save_pretrained(repo_dir)
    tokenizer.save_pretrained(repo_dir)
    return repo_dir


def _fake_quantize_noop(model: Any, tokenizer: Any, repo_dir: Path, local_out: Path,
                         params: dict[str, Any], device: str, calibration_texts: list[str]) -> None:
    # Stands in for llm-compressor/bitsandbytes: this test proves the shared runner's
    # download -> load -> measure -> quantize -> reload -> measure -> upload plumbing
    # works end to end on CPU, not that a specific third-party library does its job.
    model.save_pretrained(local_out)
    tokenizer.save_pretrained(local_out)


def test_run_llm_gpu_quantize_cpu_mode_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MF_LLM_DEVICE", "cpu")
    repo_dir = _tiny_llama_repo(tmp_path)

    def _fake_download(repo_id: str, token: str | None, local_dir: Path, **kwargs: Any) -> Path:
        import shutil

        shutil.copytree(repo_dir, local_dir, dirs_exist_ok=True)
        return local_dir

    monkeypatch.setattr(llm_gpu_common, "download_hf_snapshot", _fake_download)
    monkeypatch.setattr(llm_gpu_common, "resolve_hf_token", lambda user_id: None)

    model = model_record(
        filename="llama.safetensors", model_format="safetensors",
        details={"repoId": "org/tiny-llama"},
    )
    s3 = FakeS3({})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)

    from modelforge_catalog.methods import METHODS

    operation = next(m for m in METHODS if m.id == "q_nf4")
    llm_gpu_common.run_llm_gpu_quantize(
        user_id="user-1", job_id="job-1", model_id="model-1", params={},
        operation=operation, control=AlwaysOkControl(), event_repo=events,
        quantize_fn=_fake_quantize_noop, needs_calibration=False, tag="test",
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert "Perplexity" in result["metrics"]
    assert result["evaluation"]["before"] > 0
    assert result["evaluation"]["after"] > 0
    assert result["downloadName"] == "llama_test.zip"
    assert any(("mf-results", result["s3Key"]) == key for key in s3.uploaded)

    stages = [event.stage for event in events.events]
    assert "Running calibration data" not in stages  # needs_calibration=False
    assert stages[0] == "Loading model"
    assert "Quantizing weights" in stages


def test_run_llm_gpu_quantize_gated_repo_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ops._llm_common import GatedModelError

    monkeypatch.setenv("MF_LLM_DEVICE", "cpu")

    def _fake_download(repo_id: str, token: str | None, local_dir: Path, **kwargs: Any) -> Path:
        raise GatedModelError("nope")

    monkeypatch.setattr(llm_gpu_common, "download_hf_snapshot", _fake_download)
    monkeypatch.setattr(llm_gpu_common, "resolve_hf_token", lambda user_id: None)

    model = model_record(
        filename="llama.safetensors", model_format="safetensors",
        details={"repoId": "org/gated"},
    )
    s3 = FakeS3({})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)

    from modelforge_catalog.methods import METHODS

    operation = next(m for m in METHODS if m.id == "q_nf4")
    llm_gpu_common.run_llm_gpu_quantize(
        user_id="user-1", job_id="job-1", model_id="model-1", params={},
        operation=operation, control=AlwaysOkControl(), event_repo=events,
        quantize_fn=_fake_quantize_noop, needs_calibration=False, tag="test",
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "gated_model"
