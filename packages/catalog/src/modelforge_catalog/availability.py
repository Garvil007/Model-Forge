"""Server-side re-check of operation availability for a model.

Port of apps/web/src/features/catalog/availability.ts's `checkAvailability` — same rules,
used by POST /api/jobs so a client can't bypass the frontend's own availability gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from .formats import FORMAT
from .models import ModelInfo, OperationSpec


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    ok: bool
    why: str | None = None


def _format_label(fmt: str) -> str:
    return FORMAT.get(fmt, fmt)


def check_availability(op: OperationSpec, model: ModelInfo) -> AvailabilityResult:
    if model.format == "gguf":
        return AvailabilityResult(
            ok=False, why="Not available for GGUF files, which are already quantized."
        )

    if model.format not in op.source_formats:
        formats = ", ".join(_format_label(f) for f in op.source_formats)
        return AvailabilityResult(
            ok=False,
            why=f"Not available for {_format_label(model.format)}. Works with {formats}.",
        )

    if op.allowed_families and model.family not in op.allowed_families:
        why = (
            "Only for language models. Change the model type if this is one."
            if "llm" in op.allowed_families
            else "Not for language models; see LLM distillation."
        )
        return AvailabilityResult(ok=False, why=why)

    if op.required_bit_width is not None and model.bits < op.required_bit_width:
        return AvailabilityResult(ok=False, why=f"Your model is already {model.bits}-bit.")

    if op.target_format is not None and op.target_format == model.format:
        return AvailabilityResult(ok=False, why="Your model is already in this format.")

    return AvailabilityResult(ok=True)
