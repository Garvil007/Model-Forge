"""Detection loader: auto-detects YOLO-zip (`images/`, `labels/`, optional `data.yaml`) vs
COCO-zip (`annotations.json` + an images directory) and normalizes both to the same
yielded shape.

Box coordinate convention (documented here since Phase 4's static-quant accuracy pass and
`core.evaluators.map_eval` both depend on it): every sample's image is resized to a
`input_size` x `input_size` square (no aspect-ratio preservation, matching
`imagefolder.load_and_preprocess_image`'s crop target), and boxes are returned in absolute
pixel coordinates **in that resized frame**, as `(class_id, x1, y1, x2, y2)` with
`x1 < x2`, `y1 < y2`. This is a simplification flagged for Phase 4 catalog review: a
production detector normally preserves aspect ratio with letterboxing, which this loader
does not do.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.validation import PreprocessSpec
from PIL import Image

from .base import DatasetFormatError, safe_extract_zip, safe_join

Box = tuple[int, float, float, float, float]
_DEFAULT_CHECK_INTERVAL = 50
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _load_resized_image(path: Path, size: int) -> np.ndarray:
    with Image.open(path) as source:
        image = source.convert("RGB").resize((size, size), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.uint8)


def _yolo_boxes(label_path: Path, size: int) -> list[Box]:
    boxes: list[Box] = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        class_id, xc, yc, w, h = int(parts[0]), *map(float, parts[1:])
        x1 = (xc - w / 2) * size
        y1 = (yc - h / 2) * size
        x2 = (xc + w / 2) * size
        y2 = (yc + h / 2) * size
        boxes.append((class_id, x1, y1, x2, y2))
    return boxes


def _load_yolo(root: Path, size: int) -> list[tuple[Path, list[Box]]]:
    images_dir, labels_dir = root / "images", root / "labels"
    samples: list[tuple[Path, list[Box]]] = []
    for image_path in sorted(images_dir.iterdir(), key=lambda p: p.name):
        if image_path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        label_path = labels_dir / f"{image_path.stem}.txt"
        samples.append((image_path, _yolo_boxes(label_path, size)))
    if not samples:
        raise DatasetFormatError("YOLO zip's images/ directory has no supported image files")
    return samples


def _load_coco(root: Path, size: int) -> list[tuple[Path, list[Box]]]:
    annotations = json.loads((root / "annotations.json").read_text(encoding="utf-8"))
    images_by_id = {entry["id"]: entry for entry in annotations.get("images", [])}
    boxes_by_image: dict[int, list[Box]] = {image_id: [] for image_id in images_by_id}
    for ann in annotations.get("annotations", []):
        image_id = ann["image_id"]
        image_info = images_by_id.get(image_id)
        if image_info is None:
            continue
        scale_x = size / image_info["width"]
        scale_y = size / image_info["height"]
        x, y, w, h = ann["bbox"]
        boxes_by_image.setdefault(image_id, []).append(
            (
                int(ann["category_id"]),
                x * scale_x,
                y * scale_y,
                (x + w) * scale_x,
                (y + h) * scale_y,
            )
        )

    images_dir = root / "images"
    samples: list[tuple[Path, list[Box]]] = []
    for image_id, image_info in images_by_id.items():
        file_name = image_info["file_name"]
        image_path = safe_join(images_dir, file_name) or safe_join(root, file_name)
        if image_path is None:
            raise DatasetFormatError(
                "COCO annotations reference a file that is missing or has an unsafe path"
            )
        samples.append((image_path, boxes_by_image.get(image_id, [])))
    if not samples:
        raise DatasetFormatError("COCO annotations.json has no images")
    return samples


class DetectionLoader:
    """Yields `(image: np.ndarray[uint8, H,W,3], boxes: list[(class_id, x1,y1,x2,y2)])`."""

    def __init__(
        self,
        zip_path: str | Path,
        extract_dir: str | Path,
        preprocess: PreprocessSpec,
        *,
        max_samples: int | None = None,
        control: Any = None,
        check_interval: int = _DEFAULT_CHECK_INTERVAL,
    ) -> None:
        root = safe_extract_zip(zip_path, extract_dir)
        size = preprocess.input_size or 224
        self._size = size
        self._max_samples = max_samples
        self._control = control
        self._check_interval = check_interval
        self._samples = self._discover(root, size)

    @staticmethod
    def _discover(root: Path, size: int) -> list[tuple[Path, list[Box]]]:
        if (root / "annotations.json").exists():
            return _load_coco(root, size)
        if (root / "images").is_dir() and (root / "labels").is_dir():
            return _load_yolo(root, size)
        raise DatasetFormatError(
            "detection zip must be either YOLO format (images/ + labels/) or COCO format "
            "(annotations.json + an images directory)"
        )

    def __iter__(self) -> Iterator[tuple[np.ndarray, list[Box]]]:
        count = 0
        for path, boxes in self._samples:
            if self._max_samples is not None and count >= self._max_samples:
                return
            if self._control is not None and count % self._check_interval == 0:
                self._control.check()
            yield _load_resized_image(path, self._size), boxes
            count += 1

    def __len__(self) -> int:
        total = len(self._samples)
        return total if self._max_samples is None else min(total, self._max_samples)


__all__ = ["DetectionLoader", "Box"]
