"""core.datasets.text: CSV/JSONL text classification loader."""

from __future__ import annotations

import json

import pytest

from core.datasets.base import DatasetFormatError
from core.datasets.text import TextClassificationLoader


def test_loads_csv_rows(tmp_path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("text,label\nhello world,0\ngoodbye,1\n", encoding="utf-8")

    loader = TextClassificationLoader(csv_path)
    rows = list(loader)

    assert rows == [("hello world", "0"), ("goodbye", "1")]


def test_loads_jsonl_rows(tmp_path) -> None:
    jsonl_path = tmp_path / "data.jsonl"
    jsonl_path.write_text(
        "\n".join(
            [
                json.dumps({"text": "a", "label": 0}),
                json.dumps({"text": "b", "label": 1}),
            ]
        ),
        encoding="utf-8",
    )

    loader = TextClassificationLoader(jsonl_path)
    rows = list(loader)

    assert rows == [("a", 0), ("b", 1)]


def test_csv_missing_label_column_raises_dataset_format_error(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("text\nhello\n", encoding="utf-8")

    with pytest.raises(DatasetFormatError):
        TextClassificationLoader(csv_path)


def test_jsonl_with_invalid_json_line_raises_dataset_format_error(tmp_path) -> None:
    jsonl_path = tmp_path / "bad.jsonl"
    jsonl_path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(DatasetFormatError):
        TextClassificationLoader(jsonl_path)


def test_unsupported_extension_raises_dataset_format_error(tmp_path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("x", encoding="utf-8")

    with pytest.raises(DatasetFormatError):
        TextClassificationLoader(path)


def test_max_samples_caps_iteration(tmp_path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("text,label\na,0\nb,1\nc,0\n", encoding="utf-8")

    loader = TextClassificationLoader(csv_path, max_samples=2)

    assert len(list(loader)) == 2
