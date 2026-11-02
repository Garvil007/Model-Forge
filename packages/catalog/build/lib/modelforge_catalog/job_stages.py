"""Per-technique job stage lists, shared by the API (status reconstruction) and the worker
(which stage labels to emit, in order).

Port of apps/web/src/mocks/jobStages.ts's `stagesForOperation` — must stay label-identical
to that file so a real job's stage checklist matches what the mock simulated during Day 5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import OperationSpec


@dataclass(frozen=True, slots=True)
class StageDef:
    label: str
    epochs: int | None = None


def stages_for_operation(op: OperationSpec, params: dict[str, Any]) -> list[StageDef]:
    if op.technique == "convert":
        return [
            StageDef("Loading model"),
            StageDef(f"Converting to {op.label}"),
            StageDef("Checking outputs match"),
        ]

    finetune = bool(params.get("finetune"))
    tune_epochs = int(params.get("epochs") or 3)
    tune: list[StageDef] = [StageDef("Fine-tuning", epochs=tune_epochs)] if finetune else []

    if op.technique == "quantization":
        needs_calibration = op.id in ("q_int8_static", "q_gptq", "q_awq") or (
            op.id == "q_gguf" and bool(params.get("imatrix"))
        )
        return [
            StageDef("Loading model"),
            *([StageDef("Running calibration data")] if needs_calibration else []),
            StageDef("Quantizing weights"),
            StageDef("Measuring accuracy"),
        ]

    if op.technique == "pruning":
        return [
            StageDef("Loading model"),
            StageDef("Scoring weights"),
            StageDef("Pruning"),
            *tune,
            StageDef("Measuring accuracy"),
        ]

    if op.technique == "distillation":
        return [
            StageDef("Loading teacher"),
            StageDef("Building student"),
            StageDef("Training student", epochs=int(params.get("epochs") or 12)),
            StageDef("Measuring accuracy"),
        ]

    if op.technique == "lowrank":
        return [
            StageDef("Loading model"),
            StageDef("Decomposing layers"),
            *tune,
            StageDef("Measuring accuracy"),
        ]

    return [
        StageDef("Loading model"),
        StageDef("Running operation"),
        StageDef("Measuring accuracy"),
    ]
