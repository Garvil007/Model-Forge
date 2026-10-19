"""Orchestration tests for ops.convert_gguf (c_gguf): plain GGUF conversion, no
quantization. Monkeypatches the llama.cpp/HF calls, same shape as
tests/test_quantize_gguf.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ops import convert_gguf
from tests._convert_fakes import (
    AlwaysOkControl,
    FakeJobEventRepository,
    FakeJobRepository,
    FakeModelRepository,
    FakeS3,
    model_record,
)


def _operation() -> Any:
    from modelforge_catalog.converts import CONVERTS

    return next(c for c in CONVERTS if c.id == "c_gguf")


def test_converts_without_quantizing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_download(repo_id: str, token: str | None, local_dir: Path, **kwargs: Any) -> Path:
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir

    def _fake_convert(hf_dir: Path, out_path: Path, outtype: str) -> None:
        assert outtype == "f16"
        out_path.write_bytes(b"fake-gguf")

    monkeypatch.setattr(convert_gguf, "download_hf_snapshot", _fake_download)
    monkeypatch.setattr(convert_gguf, "resolve_hf_token", lambda user_id: None)
    monkeypatch.setattr(convert_gguf, "convert_hf_to_gguf", _fake_convert)

    model = model_record(
        filename="llama.safetensors", model_format="safetensors",
        details={"repoId": "org/tiny-llama"},
    )
    s3 = FakeS3({})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)

    convert_gguf.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={"outtype": "f16"},
        operation=_operation(), control=AlwaysOkControl(), event_repo=events,
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["downloadName"] == "llama.gguf"
    stages = [event.stage for event in events.events]
    assert stages == ["Loading model", "Converting to GGUF", "Checking outputs match"]


def test_gated_repo_fails_with_gated_model_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from ops._llm_common import GatedModelError

    def _fake_download(repo_id: str, token: str | None, local_dir: Path, **kwargs: Any) -> Path:
        raise GatedModelError("nope")

    monkeypatch.setattr(convert_gguf, "download_hf_snapshot", _fake_download)
    monkeypatch.setattr(convert_gguf, "resolve_hf_token", lambda user_id: None)

    model = model_record(
        filename="llama.safetensors", model_format="safetensors",
        details={"repoId": "org/gated-model"},
    )
    s3 = FakeS3({})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)

    convert_gguf.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params={"outtype": "f16"},
        operation=_operation(), control=AlwaysOkControl(), event_repo=events,
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "gated_model"
