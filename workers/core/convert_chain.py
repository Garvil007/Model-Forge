"""Shared helper for conversions that genuinely need more than one real conversion hop
inside a single job.

Most Convert-tab targets have a single library that goes straight from the declared
source format to the target (`onnx2tf` for onnx->tflite, `ultralytics`'s own exporter for
any yolo->X, `openvino.convert_model` for onnx/keras/torch->openvino, ...), so they don't
need this. The one place a real multi-hop chain is used is a Hugging Face `safetensors`
checkpoint being converted to OpenVINO IR: there's no library that goes directly from raw
safetensors weights to OpenVINO, but Optimum can export the HF repo straight to ONNX, and
`openvino.convert_model` takes it from there — so `convert_openvino.py` runs that as a
two-hop chain through this helper rather than a bespoke one-off loop.

A bare PyTorch `torch` (state_dict) source never participates in a chain here: it has no
architecture to export in the first place (see `workers/ops/fp_cast.py`'s and
`workers/ops/quantize_dynamic.py`'s docstrings for why this project never calls
`torch.load(..., weights_only=False)` on an untrusted upload) — every `convert_*.py` op
refuses it outright rather than pretending a chain could rescue it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HopFn = Callable[[Path, Path], None]


class ChainHopError(Exception):
    """Raised when one hop in a conversion chain fails; carries which hop failed so the
    caller can report a precise error message instead of a generic one."""

    def __init__(self, hop_label: str, original: Exception) -> None:
        super().__init__(f"{hop_label} failed: {original}")
        self.hop_label = hop_label
        self.original = original


@dataclass(frozen=True, slots=True)
class ChainHop:
    label: str
    fn: HopFn
    suffix: str


def run_chain(
    hops: tuple[ChainHop, ...],
    path_in: Path,
    path_out: Path,
    *,
    tmpdir: Path,
    event_repo: Any,
    user_id: str,
    job_id: str,
    stage: str,
) -> None:
    """Runs `hops` in order, `path_in` -> ... -> `path_out`, emitting one progress event
    per hop under the existing `stage` label (the prototype-fixed "Converting to X" stage
    from `job_stages.py` — a chain's hops are sub-progress within that one stage, never new
    top-level stages). Each intermediate file lives under `tmpdir`."""
    current = path_in
    total = len(hops)
    for index, hop in enumerate(hops, start=1):
        event_repo.append(
            user_id, job_id, stage=stage, message=f"Step {index}/{total}: {hop.label}"
        )
        is_last = index == total
        target = path_out if is_last else tmpdir / f"hop{index}{hop.suffix}"
        try:
            hop.fn(current, target)
        except Exception as error:  # noqa: BLE001 — reclassified by the caller
            raise ChainHopError(hop.label, error) from error
        current = target


__all__ = ["ChainHop", "ChainHopError", "run_chain"]
