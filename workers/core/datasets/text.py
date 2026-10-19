"""Text classification loader: CSV or JSONL with `text` and `label` columns/fields."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .base import DatasetFormatError

_DEFAULT_CHECK_INTERVAL = 200


def _read_csv(path: Path) -> list[tuple[str, str | int]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or {"text", "label"} - set(reader.fieldnames):
            raise DatasetFormatError("CSV dataset must have 'text' and 'label' columns")
        return [(row["text"], row["label"]) for row in reader]


def _read_jsonl(path: Path) -> list[tuple[str, str | int]]:
    rows: list[tuple[str, str | int]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetFormatError(f"line {line_number} is not valid JSON") from error
        if "text" not in entry or "label" not in entry:
            raise DatasetFormatError(f"line {line_number} is missing 'text' or 'label'")
        rows.append((entry["text"], entry["label"]))
    return rows


class TextClassificationLoader:
    """Yields `(text: str, label: int | str)` from a CSV or JSONL file."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_samples: int | None = None,
        control: Any = None,
        check_interval: int = _DEFAULT_CHECK_INTERVAL,
    ) -> None:
        file_path = Path(path)
        if file_path.suffix.lower() == ".csv":
            rows = _read_csv(file_path)
        elif file_path.suffix.lower() == ".jsonl":
            rows = _read_jsonl(file_path)
        else:
            raise DatasetFormatError(f"unsupported text dataset extension {file_path.suffix!r}")
        if not rows:
            raise DatasetFormatError(f"{file_path} has no rows")
        self._rows = rows
        self._max_samples = max_samples
        self._control = control
        self._check_interval = check_interval

    def __iter__(self) -> Iterator[tuple[str, str | int]]:
        count = 0
        for text, label in self._rows:
            if self._max_samples is not None and count >= self._max_samples:
                return
            if self._control is not None and count % self._check_interval == 0:
                self._control.check()
            yield text, label
            count += 1

    def __len__(self) -> int:
        total = len(self._rows)
        return total if self._max_samples is None else min(total, self._max_samples)


__all__ = ["TextClassificationLoader"]
