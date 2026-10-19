"""Top-1 / top-k accuracy for a classifier (image_cls) given logits vs an int label."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from .base import EvalResult, ModelRunnerProtocol


class TopKAccuracyEvaluator:
    """`k=1` is plain top-1 accuracy; `k=5` is the usual ImageNet-style top-5 metric."""

    def __init__(self, k: int = 1) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        self._k = k

    def evaluate(
        self, runner: ModelRunnerProtocol, loader: Iterable[Any], max_samples: int
    ) -> EvalResult:
        correct = 0
        total = 0
        for inputs, label in loader:
            if total >= max_samples:
                break
            logits = np.asarray(runner.predict(inputs[np.newaxis, ...])).reshape(-1)
            top_indices = np.argsort(logits)[::-1][: self._k]
            if int(label) in top_indices.tolist():
                correct += 1
            total += 1

        if total == 0:
            raise ValueError("no samples were available to evaluate")
        accuracy = correct / total
        metric_name = "Top-1 accuracy" if self._k == 1 else f"Top-{self._k} accuracy"
        return EvalResult(metric_name=metric_name, value=accuracy, unit="%", samples_used=total)


__all__ = ["TopKAccuracyEvaluator"]
