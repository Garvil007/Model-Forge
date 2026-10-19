"""core.datasets.lm: txt/jsonl language-modeling loader, no labels."""

from __future__ import annotations

import json

import pytest

from core.datasets.base import DatasetFormatError
from core.datasets.lm import LanguageModelingLoader


def test_chunks_txt_file_by_chunk_chars(tmp_path) -> None:
    path = tmp_path / "corpus.txt"
    path.write_text("abcdefghij", encoding="utf-8")

    loader = LanguageModelingLoader(path, chunk_chars=4)
    chunks = list(loader)

    assert chunks == ["abcd", "efgh", "ij"]


def test_jsonl_yields_text_field_per_line(tmp_path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        "\n".join([json.dumps({"text": "hello"}), json.dumps({"text": "world"})]),
        encoding="utf-8",
    )

    loader = LanguageModelingLoader(path)
    chunks = list(loader)

    assert chunks == ["hello", "world"]


def test_empty_txt_file_raises_dataset_format_error(tmp_path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("   ", encoding="utf-8")

    with pytest.raises(DatasetFormatError):
        LanguageModelingLoader(path)


def test_jsonl_missing_text_field_raises_dataset_format_error(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"label": 0}), encoding="utf-8")

    with pytest.raises(DatasetFormatError):
        LanguageModelingLoader(path)


def test_max_samples_caps_chunk_iteration(tmp_path) -> None:
    path = tmp_path / "corpus.txt"
    path.write_text("abcdefghij", encoding="utf-8")

    loader = LanguageModelingLoader(path, chunk_chars=2, max_samples=2)

    assert len(list(loader)) == 2
