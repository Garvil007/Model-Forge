"""core.datasets.base: zip-slip-safe extraction and safe .npy loading."""

from __future__ import annotations

import zipfile

import numpy as np
import pytest

from core.datasets.base import (
    DatasetExtractionError,
    DatasetFormatError,
    load_npy_safely,
    safe_extract_zip,
)


def _make_zip(path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def test_extracts_a_valid_zip(tmp_path) -> None:
    zip_path = tmp_path / "data.zip"
    _make_zip(zip_path, {"a/1.txt": b"hello", "a/2.txt": b"world"})

    dest = safe_extract_zip(zip_path, tmp_path / "out")

    assert (dest / "a" / "1.txt").read_bytes() == b"hello"
    assert (dest / "a" / "2.txt").read_bytes() == b"world"


def test_malformed_zip_raises_dataset_format_error(tmp_path) -> None:
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip file")

    with pytest.raises(DatasetFormatError):
        safe_extract_zip(bad_zip, tmp_path / "out")


def test_zip_slip_entry_is_rejected(tmp_path) -> None:
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../../escape.txt": b"pwned"})

    with pytest.raises(DatasetExtractionError):
        safe_extract_zip(zip_path, tmp_path / "out")

    assert not (tmp_path / "escape.txt").exists()


def test_absolute_path_entry_is_rejected(tmp_path) -> None:
    zip_path = tmp_path / "evil_abs.zip"
    _make_zip(zip_path, {"/etc/passwd": b"pwned"})

    with pytest.raises(DatasetExtractionError):
        safe_extract_zip(zip_path, tmp_path / "out")


def test_too_many_files_is_rejected(tmp_path) -> None:
    zip_path = tmp_path / "many.zip"
    _make_zip(zip_path, {f"f{i}.txt": b"x" for i in range(10)})

    with pytest.raises(DatasetExtractionError):
        safe_extract_zip(zip_path, tmp_path / "out", max_files=5)


def test_oversized_zip_is_rejected(tmp_path) -> None:
    zip_path = tmp_path / "big.zip"
    _make_zip(zip_path, {"big.bin": b"x" * 1000})

    with pytest.raises(DatasetExtractionError):
        safe_extract_zip(zip_path, tmp_path / "out", max_total_bytes=100)


def test_load_npy_safely_rejects_pickled_object_arrays(tmp_path) -> None:
    npy_path = tmp_path / "pickled.npy"
    object_array = np.array([{"a": 1}], dtype=object)
    np.save(npy_path, object_array, allow_pickle=True)

    with pytest.raises(ValueError):
        load_npy_safely(npy_path)


def test_load_npy_safely_loads_plain_numeric_array(tmp_path) -> None:
    npy_path = tmp_path / "plain.npy"
    np.save(npy_path, np.array([1.0, 2.0, 3.0], dtype=np.float32))

    array = load_npy_safely(npy_path)

    assert np.array_equal(array, np.array([1.0, 2.0, 3.0], dtype=np.float32))
