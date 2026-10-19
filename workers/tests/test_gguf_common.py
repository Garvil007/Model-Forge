"""Tests for ops._gguf_common's subprocess wrappers, monkeypatching subprocess.run
rather than needing a real llama.cpp build in this environment (no Docker/compiled
llama.cpp here — see docs/PROGRESS.md's Day 14 entry)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from ops import _gguf_common as gguf_common


def _fake_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_convert_hf_to_gguf_invokes_convert_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        captured["args"] = args
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gguf_common.convert_hf_to_gguf(tmp_path / "hf_repo", tmp_path / "out.gguf", "f16")

    args = captured["args"]
    assert args[1].endswith("convert_hf_to_gguf.py")
    assert str(tmp_path / "hf_repo") in args
    assert "--outtype" in args and "f16" in args
    assert "--outfile" in args and str(tmp_path / "out.gguf") in args


def test_build_imatrix_invokes_llama_imatrix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        captured["args"] = args
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gguf_common.build_imatrix(
        tmp_path / "base.gguf", tmp_path / "calib.txt", tmp_path / "imatrix.dat"
    )

    args = captured["args"]
    assert args[0].endswith("llama-imatrix")
    assert str(tmp_path / "base.gguf") in args
    assert str(tmp_path / "calib.txt") in args
    assert str(tmp_path / "imatrix.dat") in args


def test_quantize_gguf_file_includes_imatrix_flag_when_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        captured["args"] = args
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gguf_common.quantize_gguf_file(
        tmp_path / "base.gguf", tmp_path / "out.gguf", "Q4_K_M",
        imatrix_path=tmp_path / "imatrix.dat",
    )

    args = captured["args"]
    assert "--imatrix" in args
    assert str(tmp_path / "imatrix.dat") in args
    assert "Q4_K_M" in args


def test_quantize_gguf_file_omits_imatrix_flag_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        captured["args"] = args
        return _fake_completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gguf_common.quantize_gguf_file(tmp_path / "base.gguf", tmp_path / "out.gguf", "Q8_0")

    assert "--imatrix" not in captured["args"]


def test_measure_perplexity_parses_final_estimate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stdout = "some log lines\nFinal estimate: PPL = 12.3456 +/- 0.0789\n"

    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return _fake_completed(stdout=stdout)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    ppl = gguf_common.measure_perplexity(tmp_path / "model.gguf", tmp_path / "calib.txt")
    assert ppl == pytest.approx(12.3456)


def test_measure_perplexity_raises_when_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return _fake_completed(stdout="no ppl line here")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    with pytest.raises(gguf_common.LlamaCppError, match="no parseable PPL"):
        gguf_common.measure_perplexity(tmp_path / "model.gguf", tmp_path / "calib.txt")


def test_run_raises_llama_cpp_error_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.CalledProcessError(returncode=1, cmd=args, stderr="llama.cpp blew up")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    with pytest.raises(gguf_common.LlamaCppError, match="llama.cpp blew up"):
        gguf_common.convert_hf_to_gguf(tmp_path / "hf_repo", tmp_path / "out.gguf", "f16")


def test_run_raises_llama_cpp_error_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        raise FileNotFoundError("no such file")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    with pytest.raises(gguf_common.LlamaCppError, match="binary not found"):
        gguf_common.measure_perplexity(tmp_path / "model.gguf", tmp_path / "calib.txt")
