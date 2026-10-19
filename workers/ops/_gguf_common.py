"""Thin subprocess wrappers around the llama.cpp tools baked into the `cpu-llm` worker
image (`workers/images/cpu-llm/`): `convert_hf_to_gguf.py` (HF repo -> GGUF),
`llama-quantize` (GGUF -> a smaller-bit-width GGUF, optionally guided by an importance
matrix), `llama-imatrix` (builds that importance matrix from calibration text), and
`llama-perplexity` (measures perplexity of a GGUF file against a text file) — used by
`quantize_gguf.py` (**q_gguf**) and `convert_gguf.py` (**c_gguf**).

Paths come from env vars with defaults matching the `cpu-llm` image's install layout, so
this module works unmodified against a locally-built llama.cpp checkout too (set the env
vars to point at it) without needing the real image to run tests.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_PPL_PATTERN = re.compile(r"Final estimate:\s*PPL\s*=\s*([0-9.]+)")


class LlamaCppError(Exception):
    """Raised when a llama.cpp tool exits non-zero; carries its stderr tail."""


def _bin(env_name: str, default_name: str) -> str:
    return os.environ.get(env_name, f"/opt/llama.cpp/build/bin/{default_name}")


def _run(args: list[str], *, label: str) -> str:
    try:
        result = subprocess.run(  # noqa: S603 — fixed llama.cpp binaries, args are our own
            args, capture_output=True, text=True, check=True
        )
    except FileNotFoundError as error:
        raise LlamaCppError(f"{label}: binary not found ({args[0]!r}): {error}") from error
    except subprocess.CalledProcessError as error:
        tail = (error.stderr or "")[-2000:]
        raise LlamaCppError(f"{label} failed (exit {error.returncode}): {tail}") from error
    return result.stdout


def convert_hf_to_gguf(hf_dir: Path, out_path: Path, outtype: str) -> None:
    """Runs llama.cpp's `convert_hf_to_gguf.py` against a downloaded HF repo directory.
    `outtype` is one of "f32"/"f16"/"bf16"/"q8_0" (both `c_gguf`'s and `q_gguf`'s base
    conversion use this — `q_gguf` always converts to "f16" first, then quantizes
    further with `quantize_gguf_file` below)."""
    script = os.environ.get(
        "MF_LLAMA_CPP_CONVERT_SCRIPT", "/opt/llama.cpp/convert_hf_to_gguf.py"
    )
    python = os.environ.get("MF_LLAMA_CPP_PYTHON", "python3")
    _run(
        [
            python, script, str(hf_dir),
            "--outfile", str(out_path),
            "--outtype", outtype,
        ],
        label="convert_hf_to_gguf.py",
    )


def build_imatrix(base_gguf: Path, calibration_text_path: Path, out_path: Path) -> None:
    """Runs `llama-imatrix` against `base_gguf` (an F16/F32 GGUF, not yet quantized) and
    `calibration_text_path`, writing the importance matrix to `out_path`."""
    _run(
        [
            _bin("MF_LLAMA_IMATRIX_BIN", "llama-imatrix"),
            "-m", str(base_gguf),
            "-f", str(calibration_text_path),
            "-o", str(out_path),
            "--chunks", "32",
        ],
        label="llama-imatrix",
    )


def quantize_gguf_file(
    base_gguf: Path, out_path: Path, qtype: str, *, imatrix_path: Path | None = None
) -> None:
    """Runs `llama-quantize` to produce `out_path` in the given GGUF quant type
    (e.g. "Q4_K_M"), optionally guided by an importance matrix."""
    args = [_bin("MF_LLAMA_QUANTIZE_BIN", "llama-quantize")]
    if imatrix_path is not None:
        args += ["--imatrix", str(imatrix_path)]
    args += [str(base_gguf), str(out_path), qtype]
    _run(args, label="llama-quantize")


def measure_perplexity(gguf_path: Path, text_path: Path, *, chunks: int = 8) -> float:
    """Runs `llama-perplexity` and parses its "Final estimate: PPL = X.XXXX" line."""
    stdout = _run(
        [
            _bin("MF_LLAMA_PERPLEXITY_BIN", "llama-perplexity"),
            "-m", str(gguf_path),
            "-f", str(text_path),
            "--chunks", str(chunks),
        ],
        label="llama-perplexity",
    )
    match = _PPL_PATTERN.search(stdout)
    if match is None:
        raise LlamaCppError(f"llama-perplexity produced no parseable PPL line: {stdout[-500:]}")
    return float(match.group(1))


__all__ = [
    "LlamaCppError",
    "build_imatrix",
    "convert_hf_to_gguf",
    "measure_perplexity",
    "quantize_gguf_file",
]
