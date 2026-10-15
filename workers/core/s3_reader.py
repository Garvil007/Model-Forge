"""A small seekable wrapper over S3 ranged GETs, for header-only detection reads."""

from __future__ import annotations

from typing import Any


class S3RangeReader:
    """Reads a key via bounded Range GETs instead of downloading the whole object.
    Detectors that only need a header (GGUF, safetensors) use this; detectors that need
    the full file (onnx, h5, torch zip members) call `read_all()` with its own size cap."""

    def __init__(self, s3_client: Any, bucket: str, key: str, size: int) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._key = key
        self.size = size
        self._pos = 0

    def seek(self, offset: int) -> None:
        self._pos = offset

    def tell(self) -> int:
        return self._pos

    def read(self, n: int) -> bytes:
        if self._pos >= self.size or n <= 0:
            return b""
        end = min(self._pos + n, self.size) - 1
        response = self._s3.get_object(
            Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}"
        )
        data = response["Body"].read()
        self._pos += len(data)
        return data

    def read_all(self, max_bytes: int) -> bytes:
        """Full-object read, capped — only for formats that need the whole file."""
        if self.size > max_bytes:
            raise ValueError(f"file is {self.size} bytes, over the {max_bytes}-byte cap")
        response = self._s3.get_object(Bucket=self._bucket, Key=self._key)
        return response["Body"].read()
