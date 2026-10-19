"""Image classification loader: a zip of `classname/*.jpg|png` folders, label = the
sorted-folder-name index. Also exposes `load_and_preprocess_image`, reused by
`detection.py` (image-only half) and `calibration.py` (plain-zip-of-images case).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.validation import PreprocessSpec
from PIL import Image

from .base import DatasetFormatError, safe_extract_zip

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_DEFAULT_CHECK_INTERVAL = 50


def load_and_preprocess_image(path: str | Path, spec: PreprocessSpec) -> np.ndarray:
    """Resize (shorter side to `input_size`) + center-crop + normalize + reorder channels.

    Returns an array shaped `(C, H, W)` for `layout="NCHW"` or `(H, W, C)` for
    `"NHWC"` — no batch dimension; callers add one before running inference.
    """
    size = spec.input_size or 224
    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        scale = size / min(width, height)
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resized = image.resize(new_size, Image.Resampling.BILINEAR)
        left = (resized.width - size) // 2
        top = (resized.height - size) // 2
        cropped = resized.crop((left, top, left + size, top + size))
        array = np.asarray(cropped, dtype=np.float32) / 255.0  # HWC, RGB

    if spec.channel_order == "BGR":
        array = array[:, :, ::-1]
    if spec.mean is not None and spec.std is not None:
        mean = np.asarray(spec.mean, dtype=np.float32)
        std = np.asarray(spec.std, dtype=np.float32)
        array = (array - mean) / std
    if spec.layout == "NCHW":
        array = np.transpose(array, (2, 0, 1))
    return np.ascontiguousarray(array, dtype=np.float32)


class ImageFolderLoader:
    """Yields `(image: np.ndarray, label: int)` from a class-named-folder zip."""

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
        self._preprocess = preprocess
        self._max_samples = max_samples
        self._control = control
        self._check_interval = check_interval
        self.class_names, self._samples = _discover_samples(root)

    def __iter__(self) -> Iterator[tuple[np.ndarray, int]]:
        count = 0
        for path, label in self._samples:
            if self._max_samples is not None and count >= self._max_samples:
                return
            if self._control is not None and count % self._check_interval == 0:
                self._control.check()
            yield load_and_preprocess_image(path, self._preprocess), label
            count += 1

    def __len__(self) -> int:
        total = len(self._samples)
        return total if self._max_samples is None else min(total, self._max_samples)


def _discover_samples(root: Path) -> tuple[list[str], list[tuple[Path, int]]]:
    class_dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    if not class_dirs:
        raise DatasetFormatError(
            "imagefolder zip must contain class-named subfolders (e.g. 'cat/', 'dog/')"
        )
    class_names = [p.name for p in class_dirs]
    samples: list[tuple[Path, int]] = []
    for label, class_dir in enumerate(class_dirs):
        for file in sorted(class_dir.iterdir(), key=lambda p: p.name):
            if file.suffix.lower() in _IMAGE_SUFFIXES:
                samples.append((file, label))
    if not samples:
        raise DatasetFormatError("no supported images found inside the imagefolder zip")
    return class_names, samples


__all__ = ["ImageFolderLoader", "load_and_preprocess_image"]
