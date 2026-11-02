"""Dataclasses describing ModelForge's operation catalog.

Mirrors the shape of ``docs/ui-prototype.html``'s TECHS/METHODS/CONVERTS arrays, minus
the JS closures: visibility rules (``show``) become declarative :class:`ShowIf` values,
and size/impact formulas stay as plain Python callables since both the API and the
workers run in-process Python rather than a browser.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Technique = Literal["quantization", "pruning", "distillation", "lowrank"]
OperationTechnique = Literal["quantization", "pruning", "distillation", "lowrank", "convert"]
Accuracy = Literal["lossless", "near-lossless", "lossy"]
Queue = Literal["cpu", "gpu"]
# "dataset" is a marker distinct from generic "file": the submitted value must be an id of a
# dataset the caller already owns (uploaded via /datasets), not an arbitrary new upload. JSON
# Schema-wise it's still just a string (see export.py's _param_schema) — the ownership/kind
# check happens in apps/api, not at the schema level.
ParamType = Literal["select", "range", "check", "number", "text", "file", "dataset"]


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """A model's known properties, as detected from its file or sample metadata."""

    format: str
    family: str
    bits: float
    params: float
    size: int


@dataclass(frozen=True, slots=True)
class ParamOption:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class ShowIf:
    """Show the param only when the named sibling param's current value equals ``equals``."""

    field: str
    equals: Any = True


@dataclass(frozen=True, slots=True)
class ParamSpec:
    name: str
    label: str
    type: ParamType
    default: Any = None
    help: str | None = None
    required: bool = False
    options: Sequence[ParamOption] = field(default_factory=tuple)
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    accept: str | None = None
    only_for: Sequence[str] = field(default_factory=tuple)
    show_if: ShowIf | None = None


SizeEstimateFn = Callable[[ModelInfo, dict[str, Any]], float | None]
ImpactEstimateFn = Callable[[ModelInfo, dict[str, Any]], float]


@dataclass(frozen=True, slots=True)
class TechniqueInfo:
    """Metadata for one compression technique, shown in the technique picker."""

    id: Technique
    name: str
    tag: str
    mechanism: str
    hardware_impact: str
    complexity: str
    bars: Sequence[float]


@dataclass(frozen=True, slots=True)
class OperationSpec:
    id: str
    technique: OperationTechnique
    label: str
    description: str
    accuracy: Accuracy
    typical_impact: str
    time_estimate: str
    source_formats: Sequence[str]
    allowed_families: Sequence[str] = field(default_factory=tuple)
    required_bit_width: float | None = None
    target_format: str | None = None
    params: Sequence[ParamSpec] = field(default_factory=tuple)
    worker_image: str = "cpu-base"
    queue: Queue = "cpu"
    size_estimate: SizeEstimateFn | None = None
    impact_estimate: ImpactEstimateFn | None = None
