"""Shared plumbing for the LLM compression ops (`quantize_gguf.py`, `convert_gguf.py`,
`quantize_gptq.py`, `quantize_awq.py`, `quantize_nf4.py`): resolving the user's Hugging
Face token, downloading a full repo snapshot (not just the single weight file
`workers/ops/import_hf.py` grabs at import time — GGUF/GPTQ/AWQ/NF4 all need the repo's
`config.json`/tokenizer files too), and a bundled default calibration text so
`imatrix`/perplexity measurement never hard-fails just because the user didn't upload one.

Security note, consistent with `workers/ops/import_hf.py`: this module never imports
`transformers`/`torch` itself and never calls `trust_remote_code=True` — only
`huggingface_hub.snapshot_download`'s plain file download. Loading the downloaded
weights through `transformers`/llama.cpp is each op module's own concern.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DEFAULT_CALIBRATION_TEXT = """\
The quick brown fox jumps over the lazy dog near the river bank. Scientists have long
studied how language models learn to predict the next word in a sentence, building
statistical patterns from vast amounts of text. Over time, these patterns capture
grammar, facts, and even some reasoning ability. A good calibration sample should be
varied enough to reflect the kinds of text a model will see in practice, covering
everyday topics, technical explanations, and simple narrative prose. When no other
sample is provided, a short general-purpose English passage like this one is used
instead, so quantization and importance-matrix calibration always has something real
to work from rather than failing outright. Reading comprehension, summarization, and
question answering all depend on a model's ability to track context across many
sentences, which is exactly what this kind of calibration text is meant to exercise.
"""


class GatedModelError(Exception):
    """Raised when the user's Hugging Face token lacks access to a gated/licensed repo,
    or the repo requires accepting its license on huggingface.co before any token can
    download it. Mapped to the `gated_model` job error code (see `classify_llm_error`),
    which `apps/web/src/features/job/JobError.tsx` already has copy for."""


class UnsupportedFormatError(Exception):
    """Raised when an LLM op has no path for the model's source/params (e.g. a
    not-yet-wired custom calibration upload)."""


def default_calibration_text() -> str:
    return _DEFAULT_CALIBRATION_TEXT


def resolve_hf_token(user_id: str, *, users_repo: Any = None) -> str | None:
    """Looks up the user's stored Hugging Face token, KMS-decrypting it the same way
    `workers/ops/import_hf.py::handle_import_hf` does. Returns `None` for a public repo
    the user never attached a token to."""
    from modelforge_db.encryption import KmsEncryptor
    from modelforge_db.repositories.users import UserRepository

    users = users_repo if users_repo is not None else UserRepository()
    return users.get_hf_token(
        user_id,
        KmsEncryptor(os.environ.get("MF_HF_TOKEN_KMS_KEY_ID", "alias/modelforge-hf-tokens")),
    )


def download_hf_snapshot(
    repo_id: str,
    token: str | None,
    local_dir: Path,
    *,
    allow_patterns: list[str] | None = None,
) -> Path:
    """Downloads a full Hugging Face repo snapshot into `local_dir`, raising
    `GatedModelError` with a clear, actionable message rather than letting
    `huggingface_hub`'s own exception leak through when the token lacks access.
    """
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError

    try:
        snapshot_download(
            repo_id=repo_id,
            token=token,
            local_dir=str(local_dir),
            allow_patterns=allow_patterns,
        )
    except GatedRepoError as error:
        raise GatedModelError(
            f"your Hugging Face token doesn't have access to {repo_id!r} — accept the "
            "model's license on huggingface.co with the same account, then make sure a "
            "valid token for that account is attached to your ModelForge account"
        ) from error
    except RepositoryNotFoundError as error:
        raise GatedModelError(
            f"{repo_id!r} wasn't found, or it's gated and no token (or an invalid one) "
            "is attached to your ModelForge account — accept the model's license on "
            "huggingface.co, then attach a valid token"
        ) from error
    return local_dir


def classify_llm_error(error: Exception) -> tuple[str, str]:
    """Shared error classification for the LLM ops, mirroring
    `workers/ops/_convert_common.py::_classify_error`'s shape.

    Checks `_convert_common.UnsupportedFormatError` too (not just this module's own) —
    `require_hf_repo_id` (reused from `_convert_common` by `convert_gguf.py`/
    `quantize_gguf.py`) raises that one, and both mean the same thing to the job record:
    a clean "no path for this input", not a crash.
    """
    from ._convert_common import UnsupportedFormatError as ConvertUnsupportedFormatError

    if isinstance(error, GatedModelError):
        return "gated_model", str(error)
    if isinstance(error, (UnsupportedFormatError, ConvertUnsupportedFormatError)):
        return "unsupported_operator", str(error)
    return "unknown", str(error)


def resolve_calibration_text(params: dict[str, Any]) -> str:
    """Picks the calibration text for GGUF's `imatrix_text` param.

    The catalog only offers an (optional) file upload with no real-file-upload plumbing
    wired for a generic "file" param type yet (unlike the "dataset" param type
    `q_int8_static`'s `calib` uses) — see `docs/PROGRESS.md`'s Day 14 entry for this
    documented gap. A bundled default always keeps imatrix/perplexity measurement
    working regardless.
    """
    return default_calibration_text()


def resolve_calibration_dataset(params: dict[str, Any], *, max_docs: int = 64) -> list[str]:
    """Resolves GPTQ/AWQ's `dataset` select param ("wikitext2" | "c4" | "custom") into a
    list of calibration text documents.

    `custom` has the same not-yet-wired-upload gap as `resolve_calibration_text` above —
    refused with a clean `UnsupportedFormatError` rather than silently falling back, so a
    user who picked it gets an honest error instead of an unexpectedly-generic result.
    """
    choice = params.get("dataset", "wikitext2")
    if choice == "custom":
        raise UnsupportedFormatError(
            "uploading custom calibration text isn't wired to worker storage yet — pick "
            "WikiText-2 or C4 instead"
        )

    name = "wikitext" if choice == "wikitext2" else "c4" if choice == "c4" else None
    if name is None:
        raise UnsupportedFormatError(f"unknown calibration dataset {choice!r}")

    try:
        import datasets as hf_datasets

        if name == "wikitext":
            dataset = hf_datasets.load_dataset("wikitext", "wikitext-2-raw-v1", split="train")
        else:
            streamed = hf_datasets.load_dataset(
                "allenai/c4", "en", split="train", streaming=True
            )
            dataset = list(streamed.take(max_docs * 4))

        texts = [row["text"] for row in dataset if row.get("text", "").strip()]
        if texts:
            return texts[:max_docs]
    except Exception:  # noqa: BLE001 — network/dataset-hub issues degrade, never crash the job
        pass

    # Offline/no-network fallback: chunk the bundled default text into several short
    # "documents" rather than failing the job over a dataset-hub outage.
    text = default_calibration_text()
    chunk = max(1, len(text) // max(1, max_docs // 8))
    chunks = [text[i : i + chunk] for i in range(0, len(text), chunk)][:max_docs]
    return chunks or [text]


__all__ = [
    "GatedModelError",
    "UnsupportedFormatError",
    "classify_llm_error",
    "default_calibration_text",
    "download_hf_snapshot",
    "resolve_calibration_dataset",
    "resolve_calibration_text",
    "resolve_hf_token",
]
