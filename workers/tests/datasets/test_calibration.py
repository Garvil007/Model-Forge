"""core.datasets.calibration: unlabeled loader for q_int8_static calibration data."""

from __future__ import annotations

import zipfile
from io import BytesIO

import numpy as np
import pytest
from modelforge_catalog.validation import PreprocessSpec
from PIL import Image

from core.datasets.base import DatasetFormatError
from core.datasets.calibration import CalibrationLoader


def _png_bytes(color: tuple[int, int, int] = (5, 6, 7)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_loads_plain_zip_of_images_without_class_subfolders(tmp_path) -> None:
    zip_path = tmp_path / "calib.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("1.png", _png_bytes())
        archive.writestr("2.png", _png_bytes())

    loader = CalibrationLoader(
        zip_path, tmp_path / "out", PreprocessSpec(input_size=16)
    )
    samples = list(loader)

    assert len(samples) == 2
    assert all(sample.shape == (3, 16, 16) for sample in samples)


def test_loads_npy_tensor_file(tmp_path) -> None:
    npy_path = tmp_path / "tensors.npy"
    np.save(npy_path, np.zeros((4, 3, 8, 8), dtype=np.float32))

    loader = CalibrationLoader(npy_path, None, PreprocessSpec())
    samples = list(loader)

    assert len(samples) == 4
    assert samples[0].shape == (3, 8, 8)


def test_npy_with_pickled_objects_is_rejected(tmp_path) -> None:
    npy_path = tmp_path / "pickled.npy"
    np.save(npy_path, np.array([{"a": 1}], dtype=object), allow_pickle=True)

    with pytest.raises(ValueError):
        CalibrationLoader(npy_path, None, PreprocessSpec())


def test_max_samples_caps_calibration_iteration(tmp_path) -> None:
    npy_path = tmp_path / "tensors.npy"
    np.save(npy_path, np.zeros((5, 2, 2), dtype=np.float32))

    loader = CalibrationLoader(npy_path, None, PreprocessSpec(), max_samples=2)

    assert len(list(loader)) == 2


def test_unsupported_extension_raises_dataset_format_error(tmp_path) -> None:
    bad_path = tmp_path / "data.bin"
    bad_path.write_bytes(b"xyz")

    with pytest.raises(DatasetFormatError):
        CalibrationLoader(bad_path, None, PreprocessSpec())


def test_zip_without_extract_dir_raises_dataset_format_error(tmp_path) -> None:
    zip_path = tmp_path / "calib.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("1.png", _png_bytes())

    with pytest.raises(DatasetFormatError):
        CalibrationLoader(zip_path, None, PreprocessSpec())
