"""Compression technique metadata (the TECHS table in the prototype)."""

from __future__ import annotations

from .models import TechniqueInfo

TECHNIQUES: tuple[TechniqueInfo, ...] = (
    TechniqueInfo(
        id="quantization",
        name="Quantization",
        tag="Fewer bits per weight",
        mechanism="Lowers bit-precision (e.g. FP32 to INT8)",
        hardware_impact="Drastically drops RAM; accelerates CPU/NPU",
        complexity="Low to medium",
        bars=(1, 0.5, 0),
    ),
    TechniqueInfo(
        id="pruning",
        name="Pruning",
        tag="Remove weights",
        mechanism="Deletes less impactful weights or channels",
        hardware_impact="Shrinks file size; accelerates structured execution",
        complexity="Medium, needs fine-tuning",
        bars=(1, 1, 0),
    ),
    TechniqueInfo(
        id="distillation",
        name="Knowledge distillation",
        tag="Train a smaller copy",
        mechanism="Trains a smaller model to copy a larger one",
        hardware_impact="Creates a native, lightweight architecture",
        complexity="High, needs retraining",
        bars=(1, 1, 1),
    ),
    TechniqueInfo(
        id="lowrank",
        name="Low-rank factorization",
        tag="Split big matrices",
        mechanism="Splits massive matrices into smaller sub-matrices",
        hardware_impact="Speeds up mathematical operations",
        complexity="Medium",
        bars=(1, 1, 0),
    ),
)
