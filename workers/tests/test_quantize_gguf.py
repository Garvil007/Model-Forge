"""Orchestration tests for ops.quantize_gguf (q_gguf): stage events, imatrix toggle,
perplexity-before/after metrics, gated-repo error classification. Monkeypatches the
llama.cpp subprocess calls and the HF download (no real llama.cpp build or network in
this environment — see docs/PROGRESS.md's Day 14 entry).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ops import quantize_gguf
from tests._convert_fakes import (
    AlwaysOkControl,
    FakeJobEventRepository,
    FakeJobRepository,
    FakeModelRepository,
    FakeS3,
    model_record,
)


def _patch_llama_cpp(
    monkeypatch: pytest.MonkeyPatch, *, before_ppl: float, after_ppl: float
) -> None:
    def _fake_download(repo_id: str, token: str | None, local_dir: Path, **kwargs: Any) -> Path:
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir

    def _fake_convert(hf_dir: Path, out_path: Path, outtype: str) -> None:
        out_path.write_bytes(b"fake-f16-gguf")

    def _fake_imatrix(base_gguf: Path, calib_path: Path, out_path: Path) -> None:
        out_path.write_bytes(b"fake-imatrix")

    def _fake_quantize(
        base_gguf: Path, out_path: Path, qtype: str, *, imatrix_path: Path | None = None
    ) -> None:
        out_path.write_bytes(b"fake-quantized-gguf")

    ppl_values = iter([before_ppl, after_ppl])

    def _fake_perplexity(gguf_path: Path, text_path: Path, *, chunks: int = 8) -> float:
        return next(ppl_values)

    monkeypatch.setattr(quantize_gguf, "download_hf_snapshot", _fake_download)
    monkeypatch.setattr(quantize_gguf, "resolve_hf_token", lambda user_id: None)
    monkeypatch.setattr(quantize_gguf, "convert_hf_to_gguf", _fake_convert)
    monkeypatch.setattr(quantize_gguf, "build_imatrix", _fake_imatrix)
    monkeypatch.setattr(quantize_gguf, "quantize_gguf_file", _fake_quantize)
    monkeypatch.setattr(quantize_gguf, "measure_perplexity", _fake_perplexity)


def _operation() -> Any:
    from modelforge_catalog.methods import METHODS

    return next(m for m in METHODS if m.id == "q_gguf")


def _run(params: dict[str, Any]) -> tuple[FakeJobRepository, FakeJobEventRepository, FakeS3]:
    model = model_record(
        filename="llama.safetensors", model_format="safetensors",
        details={"repoId": "org/tiny-llama"},
    )
    s3 = FakeS3({})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)
    quantize_gguf.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params,
        operation=_operation(), control=AlwaysOkControl(), event_repo=events,
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )
    return jobs, events, s3


def test_succeeds_with_imatrix_and_reports_perplexity(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llama_cpp(monkeypatch, before_ppl=9.0, after_ppl=9.5)
    jobs, events, s3 = _run({"qtype": "Q4_K_M", "imatrix": True})

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["metrics"]["Perplexity"] == "9 before, 9.5 after (lower is better)"
    assert result["downloadName"] == "llama_Q4_K_M.gguf"
    assert any(("mf-results", result["s3Key"]) == key for key in s3.uploaded)

    stages = [event.stage for event in events.events]
    assert stages == [
        "Loading model", "Loading model", "Running calibration data",
        "Quantizing weights", "Measuring accuracy",
    ]


def test_skips_calibration_stage_when_imatrix_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llama_cpp(monkeypatch, before_ppl=9.0, after_ppl=12.0)
    jobs, events, _ = _run({"qtype": "Q2_K", "imatrix": False})

    assert jobs.calls[-1]["status"] == "succeeded"
    stages = [event.stage for event in events.events]
    assert "Running calibration data" not in stages


def test_gated_repo_fails_the_job_with_gated_model_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from ops._llm_common import GatedModelError

    def _fake_download(repo_id: str, token: str | None, local_dir: Path, **kwargs: Any) -> Path:
        raise GatedModelError(f"your token doesn't have access to {repo_id!r}")

    monkeypatch.setattr(quantize_gguf, "download_hf_snapshot", _fake_download)
    monkeypatch.setattr(quantize_gguf, "resolve_hf_token", lambda user_id: None)

    jobs, _, _ = _run({"qtype": "Q4_K_M", "imatrix": True})

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "gated_model"


def test_missing_repo_id_fails_with_unsupported_operator() -> None:
    model = model_record(filename="model.safetensors", model_format="safetensors", details={})
    s3 = FakeS3({})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)
    quantize_gguf.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={"qtype": "Q4_K_M"},
        operation=_operation(), control=AlwaysOkControl(), event_repo=events,
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"
