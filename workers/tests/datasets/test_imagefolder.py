"""core.datasets.imagefolder: class-named-folder zip loader."""

from __future__ import annotations

import zipfile
from io import BytesIO

import numpy as np
import pytest
from modelforge_catalog.validation import PreprocessSpec
from PIL import Image

from core.datasets.base import DatasetFormatError
from core.datasets.imagefolder import ImageFolderLoader, load_and_preprocess_image


def _png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (32, 32)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_imagefolder_zip(path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("cat/1.png", _png_bytes((255, 0, 0)))
        archive.writestr("cat/2.png", _png_bytes((255, 0, 0)))
        archive.writestr("dog/1.png", _png_bytes((0, 255, 0)))


def test_loads_samples_with_sorted_folder_index_as_label(tmp_path) -> None:
    zip_path = tmp_path / "images.zip"
    _make_imagefolder_zip(zip_path)

    loader = ImageFolderLoader(zip_path, tmp_path / "out", PreprocessSpec())
    samples = list(loader)

    assert loader.class_names == ["cat", "dog"]
    assert len(samples) == 3
    labels = sorted(label for _, label in samples)
    assert labels == [0, 0, 1]


def test_preprocessed_image_has_nchw_shape_and_normalized_values(tmp_path) -> None:
    zip_path = tmp_path / "images.zip"
    _make_imagefolder_zip(zip_path)
    loader = ImageFolderLoader(zip_path, tmp_path / "out", PreprocessSpec(input_size=16))

    image, _label = next(iter(loader))

    assert image.shape == (3, 16, 16)
    assert image.dtype == np.float32


def test_nhwc_layout_is_respected(tmp_path) -> None:
    zip_path = tmp_path / "images.zip"
    _make_imagefolder_zip(zip_path)
    loader = ImageFolderLoader(
        zip_path, tmp_path / "out", PreprocessSpec(input_size=16, layout="NHWC")
    )

    image, _label = next(iter(loader))

    assert image.shape == (16, 16, 3)


def test_max_samples_caps_iteration(tmp_path) -> None:
    zip_path = tmp_path / "images.zip"
    _make_imagefolder_zip(zip_path)
    loader = ImageFolderLoader(zip_path, tmp_path / "out", PreprocessSpec(), max_samples=1)

    assert len(list(loader)) == 1
    assert len(loader) == 1


def test_control_check_is_called_during_iteration(tmp_path) -> None:
    zip_path = tmp_path / "images.zip"
    _make_imagefolder_zip(zip_path)

    class _Control:
        def __init__(self) -> None:
            self.calls = 0

        def check(self) -> None:
            self.calls += 1

    control = _Control()
    loader = ImageFolderLoader(
        zip_path, tmp_path / "out", PreprocessSpec(), control=control, check_interval=1
    )
    list(loader)

    assert control.calls == 3


def test_no_class_subfolders_raises_dataset_format_error(tmp_path) -> None:
    zip_path = tmp_path / "flat.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("1.png", _png_bytes((255, 0, 0)))

    with pytest.raises(DatasetFormatError):
        ImageFolderLoader(zip_path, tmp_path / "out", PreprocessSpec())


def test_load_and_preprocess_image_resizes_to_input_size(tmp_path) -> None:
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (64, 32), (10, 20, 30)).save(image_path)

    array = load_and_preprocess_image(image_path, PreprocessSpec(input_size=16))

    assert array.shape == (3, 16, 16)
