"""core.datasets.detection: YOLO-zip and COCO-zip auto-detection."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest
from modelforge_catalog.validation import PreprocessSpec
from PIL import Image

from core.datasets.base import DatasetFormatError
from core.datasets.detection import DetectionLoader


def _png_bytes(size: tuple[int, int] = (100, 100)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (1, 2, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_loads_yolo_format_zip_with_normalized_boxes(tmp_path) -> None:
    zip_path = tmp_path / "yolo.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("images/img1.png", _png_bytes())
        # class 0, box centered at (0.5, 0.5), full-width/height
        archive.writestr("labels/img1.txt", "0 0.5 0.5 1.0 1.0\n")

    loader = DetectionLoader(zip_path, tmp_path / "out", PreprocessSpec(input_size=32))
    samples = list(loader)

    assert len(samples) == 1
    image, boxes = samples[0]
    assert image.shape == (32, 32, 3)
    assert boxes == [(0, 0.0, 0.0, 32.0, 32.0)]


def test_loads_coco_format_zip_scaling_boxes_to_resized_image(tmp_path) -> None:
    zip_path = tmp_path / "coco.zip"
    annotations = {
        "images": [{"id": 1, "file_name": "img1.png", "width": 100, "height": 100}],
        "annotations": [{"image_id": 1, "category_id": 3, "bbox": [10, 10, 50, 50]}],
    }
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("annotations.json", json.dumps(annotations))
        archive.writestr("images/img1.png", _png_bytes((100, 100)))

    loader = DetectionLoader(zip_path, tmp_path / "out", PreprocessSpec(input_size=50))
    samples = list(loader)

    assert len(samples) == 1
    _image, boxes = samples[0]
    # original bbox [10,10,50,50] at scale 50/100=0.5 -> x1=5,y1=5,x2=30,y2=30
    assert boxes == [(3, 5.0, 5.0, 30.0, 30.0)]


def test_coco_file_name_path_traversal_is_rejected(tmp_path) -> None:
    zip_path = tmp_path / "coco.zip"
    annotations = {
        "images": [
            {"id": 1, "file_name": "../../etc/passwd", "width": 100, "height": 100}
        ],
        "annotations": [],
    }
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("annotations.json", json.dumps(annotations))
        archive.writestr("images/placeholder.png", _png_bytes((100, 100)))

    with pytest.raises(DatasetFormatError):
        DetectionLoader(zip_path, tmp_path / "out", PreprocessSpec(input_size=50))


def test_neither_format_raises_dataset_format_error(tmp_path) -> None:
    zip_path = tmp_path / "unknown.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("readme.txt", "nothing useful here")

    with pytest.raises(DatasetFormatError):
        DetectionLoader(zip_path, tmp_path / "out", PreprocessSpec())


def test_max_samples_caps_detection_iteration(tmp_path) -> None:
    zip_path = tmp_path / "yolo.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("images/img1.png", _png_bytes())
        archive.writestr("images/img2.png", _png_bytes())
        archive.writestr("labels/img1.txt", "0 0.5 0.5 1.0 1.0\n")
        archive.writestr("labels/img2.txt", "0 0.5 0.5 1.0 1.0\n")

    loader = DetectionLoader(zip_path, tmp_path / "out", PreprocessSpec(), max_samples=1)

    assert len(list(loader)) == 1
