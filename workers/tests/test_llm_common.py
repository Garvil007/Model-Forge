"""Tests for ops._llm_common: the parts that don't need torch/transformers installed
(gated-repo classification, calibration-text/dataset resolution, token lookup) — the
GPU-ops test files cover the parts that do, skip-gated where those aren't installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ops import _convert_common
from ops import _llm_common as llm_common


class _FakeUsers:
    def __init__(self, token: str | None) -> None:
        self._token = token

    def get_hf_token(self, user_id: str, encryptor: Any) -> str | None:
        return self._token


def test_default_calibration_text_is_nonempty() -> None:
    text = llm_common.default_calibration_text()
    assert isinstance(text, str)
    assert len(text) > 100


def test_resolve_calibration_text_falls_back_to_default() -> None:
    assert llm_common.resolve_calibration_text({}) == llm_common.default_calibration_text()


def test_resolve_hf_token_returns_none_when_unset() -> None:
    token = llm_common.resolve_hf_token("user-1", users_repo=_FakeUsers(None))
    assert token is None


def test_resolve_hf_token_returns_decrypted_token() -> None:
    token = llm_common.resolve_hf_token("user-1", users_repo=_FakeUsers("hf_abc123"))
    assert token == "hf_abc123"


def test_classify_llm_error_maps_gated_model() -> None:
    code, message = llm_common.classify_llm_error(llm_common.GatedModelError("nope"))
    assert code == "gated_model"
    assert message == "nope"


def test_classify_llm_error_maps_llm_common_unsupported_format() -> None:
    code, _ = llm_common.classify_llm_error(llm_common.UnsupportedFormatError("x"))
    assert code == "unsupported_operator"


def test_classify_llm_error_maps_convert_common_unsupported_format() -> None:
    # require_hf_repo_id (reused from _convert_common by the GGUF ops) raises its own
    # UnsupportedFormatError class, not _llm_common's — both must classify the same way.
    code, _ = llm_common.classify_llm_error(_convert_common.UnsupportedFormatError("x"))
    assert code == "unsupported_operator"


def test_classify_llm_error_maps_unknown_error_to_unknown() -> None:
    code, _ = llm_common.classify_llm_error(RuntimeError("boom"))
    assert code == "unknown"


def test_resolve_calibration_dataset_rejects_custom_upload() -> None:
    with pytest.raises(llm_common.UnsupportedFormatError, match="wired"):
        llm_common.resolve_calibration_dataset({"dataset": "custom"})


def test_resolve_calibration_dataset_rejects_unknown_choice() -> None:
    with pytest.raises(llm_common.UnsupportedFormatError, match="unknown"):
        llm_common.resolve_calibration_dataset({"dataset": "nonsense"})


def test_resolve_calibration_dataset_falls_back_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    # `datasets` isn't installed in every environment that runs this suite (it's part of
    # the gpu-ops extra) — simulate that exact failure mode (ImportError) rather than
    # requiring network access or the real package to prove the offline fallback works.
    import builtins

    real_import = builtins.__import__

    def _raise_for_datasets(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "datasets":
            raise ImportError("simulated: datasets not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_for_datasets)
    texts = llm_common.resolve_calibration_dataset({"dataset": "wikitext2"}, max_docs=4)
    assert texts
    assert all(isinstance(t, str) and t.strip() for t in texts)
    assert len(texts) <= 4


def _fake_http_response() -> Any:
    import httpx2

    return httpx2.Response(403, request=httpx2.Request("GET", "https://huggingface.co"))


def test_download_hf_snapshot_raises_gated_model_error_on_gated_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from huggingface_hub.utils import GatedRepoError

    def _raise_gated(**kwargs: Any) -> None:
        raise GatedRepoError("gated", response=_fake_http_response())

    monkeypatch.setattr("huggingface_hub.snapshot_download", _raise_gated)
    with pytest.raises(llm_common.GatedModelError, match="accept the"):
        llm_common.download_hf_snapshot("meta-llama/Llama-3.2-1B", "bad-token", tmp_path)


def test_download_hf_snapshot_raises_gated_model_error_on_repo_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from huggingface_hub.utils import RepositoryNotFoundError

    def _raise_not_found(**kwargs: Any) -> None:
        raise RepositoryNotFoundError("missing", response=_fake_http_response())

    monkeypatch.setattr("huggingface_hub.snapshot_download", _raise_not_found)
    with pytest.raises(llm_common.GatedModelError):
        llm_common.download_hf_snapshot("some/repo", None, tmp_path)
