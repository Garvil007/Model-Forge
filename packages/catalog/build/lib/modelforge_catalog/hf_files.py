"""Hugging Face repo file selection, shared by the API (size estimate) and worker (download)."""

from __future__ import annotations

from dataclasses import dataclass

_WEIGHT_SUFFIX_PRIORITY: tuple[str, ...] = (
    ".safetensors",
    ".bin",
    ".gguf",
    ".onnx",
    ".tflite",
    ".keras",
    ".h5",
)

_METADATA_NAMES: frozenset[str] = frozenset(
    {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "tokenizer.model",
        "special_tokens_map.json",
        "generation_config.json",
        "vocab.txt",
        "merges.txt",
    }
)
_MAX_METADATA_FILE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class HfRepoFile:
    path: str
    size: int


def _weight_suffix(path: str) -> str | None:
    lower = path.lower()
    for suffix in _WEIGHT_SUFFIX_PRIORITY:
        if lower.endswith(suffix):
            return suffix
    return None


def select_repo_files(siblings: list[HfRepoFile]) -> list[HfRepoFile]:
    """Pick the weight file(s) to download plus small metadata files.

    Priority: safetensors (all shards) > bin > gguf > onnx > tflite > keras/h5. Within a
    suffix, sharded safetensors/bin files (``model-00001-of-00005.safetensors``) are all
    kept together; otherwise only the largest single file for that suffix is kept.
    """
    by_suffix: dict[str, list[HfRepoFile]] = {}
    for file in siblings:
        suffix = _weight_suffix(file.path)
        if suffix is not None:
            by_suffix.setdefault(suffix, []).append(file)

    chosen: list[HfRepoFile] = []
    for suffix in _WEIGHT_SUFFIX_PRIORITY:
        candidates = by_suffix.get(suffix)
        if not candidates:
            continue
        sharded = [f for f in candidates if "-of-" in f.path.rsplit("/", 1)[-1]]
        chosen = sharded if sharded else [max(candidates, key=lambda f: f.size)]
        break

    metadata = [
        f
        for f in siblings
        if f.path.rsplit("/", 1)[-1] in _METADATA_NAMES and f.size <= _MAX_METADATA_FILE_BYTES
    ]
    return chosen + metadata


def total_bytes(files: list[HfRepoFile]) -> int:
    return sum(f.size for f in files)
