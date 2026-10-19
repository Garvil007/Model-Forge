"""Language-modeling loader: a `.txt` file chunked into fixed-size character windows, or a
`.jsonl` file with a `text` field per line. No label — language modeling is
self-supervised, so this yields `text: str` chunks only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .base import DatasetFormatError

_DEFAULT_CHUNK_CHARS = 2000
_DEFAULT_CHECK_INTERVAL = 200


def _chunk_text(text: str, chunk_chars: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [stripped[i : i + chunk_chars] for i in range(0, len(stripped), chunk_chars)]


def _read_jsonl_chunks(path: Path) -> list[str]:
    chunks: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetFormatError(f"line {line_number} is not valid JSON") from error
        if "text" not in entry:
            raise DatasetFormatError(f"line {line_number} is missing a 'text' field")
        chunks.append(entry["text"])
    return chunks


class LanguageModelingLoader:
    """Yields `text: str` chunks from a `.txt` or `.jsonl` file (no label)."""

    def __init__(
        self,
        path: str | Path,
        *,
        chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        max_samples: int | None = None,
        control: Any = None,
        check_interval: int = _DEFAULT_CHECK_INTERVAL,
    ) -> None:
        file_path = Path(path)
        if file_path.suffix.lower() == ".txt":
            chunks = _chunk_text(file_path.read_text(encoding="utf-8"), chunk_chars)
        elif file_path.suffix.lower() == ".jsonl":
            chunks = _read_jsonl_chunks(file_path)
        else:
            raise DatasetFormatError(f"unsupported lm dataset extension {file_path.suffix!r}")
        if not chunks:
            raise DatasetFormatError(f"{file_path} produced no text chunks")
        self._chunks = chunks
        self._max_samples = max_samples
        self._control = control
        self._check_interval = check_interval

    def __iter__(self) -> Iterator[str]:
        count = 0
        for chunk in self._chunks:
            if self._max_samples is not None and count >= self._max_samples:
                return
            if self._control is not None and count % self._check_interval == 0:
                self._control.check()
            yield chunk
            count += 1

    def __len__(self) -> int:
        total = len(self._chunks)
        return total if self._max_samples is None else min(total, self._max_samples)


__all__ = ["LanguageModelingLoader"]
