"""Shared loader protocol and the zip-slip-safe extraction helper every zip-based loader
must use instead of raw `zipfile.ZipFile.extractall`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, runtime_checkable

import numpy as np

_DEFAULT_MAX_FILES = 20_000
_DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


class DatasetFormatError(Exception):
    """Raised when a dataset upload doesn't match any supported format for its task type."""


class DatasetExtractionError(Exception):
    """Raised when a zip archive fails safety checks (zip-slip, oversized, too many files)."""


@runtime_checkable
class DatasetLoader(Protocol):
    """Iterates `(inputs, label)` sample pairs.

    `inputs` is a numpy array already preprocessed (shape/dtype depend on task type;
    image_cls/detection yield a single image array per sample, no batch dimension —
    callers add one before calling `ModelRunnerProtocol.predict`). `label` is an `int`
    class index for image_cls/text_cls, a list of detection boxes for detection, and may
    be absent entirely for self-supervised loaders (`lm.py`) or unlabeled ones
    (`calibration.py`), which document their own yielded shape instead of conforming here.
    """

    def __iter__(self) -> Any: ...

    def __len__(self) -> int: ...


def _assert_safe_member(name: str, dest_dir: Path) -> Path:
    """Resolve a zip member's target path, rejecting anything that escapes `dest_dir`."""
    posix_name = PurePosixPath(name)
    if posix_name.is_absolute() or ".." in posix_name.parts:
        raise DatasetExtractionError(f"zip entry {name!r} has an unsafe path")
    target = (dest_dir / Path(*posix_name.parts)).resolve()
    try:
        target.relative_to(dest_dir)
    except ValueError as error:
        raise DatasetExtractionError(
            f"zip entry {name!r} escapes the extraction directory"
        ) from error
    return target


def safe_join(base_dir: Path, name: str) -> Path | None:
    """Resolve `name` against `base_dir`, rejecting any path that escapes it.

    Returns `None` if the resolved path doesn't exist or `name` is itself unsafe (absolute
    or containing `..`), rather than raising, so callers can try multiple candidate base
    directories (e.g. COCO's `images/` then its root) without special-casing each failure.
    """
    posix_name = PurePosixPath(name)
    if posix_name.is_absolute() or ".." in posix_name.parts:
        return None
    base = base_dir.resolve()
    candidate = (base / Path(*posix_name.parts)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def safe_extract_zip(
    zip_path: str | Path,
    dest_dir: str | Path,
    *,
    max_files: int = _DEFAULT_MAX_FILES,
    max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
) -> Path:
    """Extract `zip_path` into `dest_dir`, rejecting zip-slip paths and oversized archives.

    Validates every member's resolved path stays inside `dest_dir` and enforces both a
    file-count cap and a total-uncompressed-size cap *before* extracting anything, so a
    malicious or malformed archive can't exhaust disk space or escape the sandbox.
    """
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            if len(infos) > max_files:
                raise DatasetExtractionError(
                    f"zip contains {len(infos)} entries, exceeding the {max_files} cap"
                )
            total_bytes = sum(info.file_size for info in infos)
            if total_bytes > max_total_bytes:
                raise DatasetExtractionError(
                    f"zip uncompressed size {total_bytes} exceeds the {max_total_bytes} cap"
                )
            targets = [(_assert_safe_member(info.filename, dest), info) for info in infos]
            for target, info in targets:
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, open(target, "wb") as destination:
                    destination.write(source.read())
    except zipfile.BadZipFile as error:
        raise DatasetFormatError(f"{zip_path} is not a valid zip archive") from error

    return dest


def load_npy_safely(path: str | Path) -> np.ndarray:
    """Load a `.npy`/`.npz` file, refusing `allow_pickle` deserialization entirely."""
    array = np.load(path, allow_pickle=False)
    if isinstance(array, np.lib.npyio.NpzFile):
        arrays = [array[name] for name in array.files]
        if not arrays:
            raise DatasetFormatError(f"{path} is an empty .npz archive")
        return arrays[0] if len(arrays) == 1 else np.concatenate(arrays, axis=0)
    return array


__all__ = [
    "DatasetFormatError",
    "DatasetExtractionError",
    "DatasetLoader",
    "safe_extract_zip",
    "safe_join",
    "load_npy_safely",
]
