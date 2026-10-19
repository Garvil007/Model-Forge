"""Shared evaluator protocol and result type."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class EvalResult:
    """One evaluator's outcome. `extra` carries secondary metrics an evaluator computes
    alongside its primary one (e.g. macro-F1 next to accuracy) without widening this
    dataclass's required shape for every caller."""

    metric_name: str
    value: float
    unit: str
    samples_used: int
    extra: dict[str, float] = field(default_factory=dict)


class ModelRunnerProtocol(Protocol):
    """Unifies ONNX/TFLite/torch/TorchScript inference — see `core.model_runner`."""

    def predict(self, batch: np.ndarray) -> np.ndarray: ...


class Evaluator(Protocol):
    def evaluate(
        self, runner: ModelRunnerProtocol, loader: Iterable[Any], max_samples: int
    ) -> EvalResult: ...


__all__ = ["EvalResult", "ModelRunnerProtocol", "Evaluator"]
