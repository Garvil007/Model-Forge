"""Unlabeled calibration loader for `q_int8_static`'s `calib` dataset param: either a
plain zip of images (no class subfolders, unlike `imagefolder.py`) or a `.npy`/`.npz` of
pre-processed tensors. Capped by `max_samples`, which the catalog's existing `samples`
param (see `packages/catalog/src/modelforge_catalog/methods.py`'s `q_int8_static`) feeds.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.validation import PreprocessSpec

from .base import DatasetFormatError, load_npy_safely, safe_extract_zip
from .imagefolder import _IMAGE_SUFFIXES, load_and_preprocess_image

_DEFAULT_CHECK_INTERVAL = 50


def _discover_images(root: Path) -> list[Path]:
    images = sorted(
        (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES),
        key=lambda p: p.as_posix(),
    )
    if not images:
        raise DatasetFormatError("calibration zip has no supported image files")
    return images


class CalibrationLoader:
    """Yields `inputs: np.ndarray` only — no labels, since calibration is unsupervised."""

    def __init__(
        self,
        path: str | Path,
        extract_dir: str | Path | None,
        preprocess: PreprocessSpec,
        *,
        max_samples: int | None = None,
        control: Any = None,
        check_interval: int = _DEFAULT_CHECK_INTERVAL,
    ) -> None:
        self._max_samples = max_samples
        self._control = control
        self._check_interval = check_interval
        file_path = Path(path)

        if file_path.suffix.lower() == ".zip":
            if extract_dir is None:
                raise DatasetFormatError("extract_dir is required for a zip calibration dataset")
            root = safe_extract_zip(file_path, extract_dir)
            image_paths = _discover_images(root)
            self._items: list[np.ndarray] | None = None
            self._image_paths: list[Path] | None = image_paths
            self._preprocess = preprocess
        elif file_path.suffix.lower() in {".npy", ".npz"}:
            array = load_npy_safely(file_path)
            self._items = list(array)
            self._image_paths = None
            self._preprocess = preprocess
        else:
            raise DatasetFormatError(
                f"unsupported calibration dataset extension {file_path.suffix!r}"
            )

    def _should_stop(self, count: int) -> bool:
        return self._max_samples is not None and count >= self._max_samples

    def _maybe_check_control(self, count: int) -> None:
        if self._control is not None and count % self._check_interval == 0:
            self._control.check()

    def __iter__(self) -> Iterator[np.ndarray]:
        count = 0
        if self._image_paths is not None:
            for image_path in self._image_paths:
                if self._should_stop(count):
                    return
                self._maybe_check_control(count)
                yield load_and_preprocess_image(image_path, self._preprocess)
                count += 1
            return

        assert self._items is not None
        for item in self._items:
            if self._should_stop(count):
                return
            self._maybe_check_control(count)
            yield np.asarray(item)
            count += 1

    def __len__(self) -> int:
        source = self._image_paths if self._image_paths is not None else self._items
        total = len(source) if source is not None else 0
        return total if self._max_samples is None else min(total, self._max_samples)


__all__ = ["CalibrationLoader"]
