"""Accuracy + macro-F1 for multi-class text classification."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from .base import EvalResult, ModelRunnerProtocol


def _macro_f1(labels: list[int], predictions: list[int]) -> float:
    classes = sorted(set(labels) | set(predictions))
    if not classes:
        return 0.0
    pairs = list(zip(labels, predictions, strict=True))
    f1_scores = []
    for cls in classes:
        true_positive = sum(1 for actual, pred in pairs if actual == cls and pred == cls)
        false_positive = sum(1 for actual, pred in pairs if actual != cls and pred == cls)
        false_negative = sum(1 for actual, pred in pairs if actual == cls and pred != cls)
        denom_p = true_positive + false_positive
        denom_r = true_positive + false_negative
        precision = true_positive / denom_p if denom_p else 0.0
        recall = true_positive / denom_r if denom_r else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1_scores.append(f1)
    return sum(f1_scores) / len(f1_scores)


class TextClassificationEvaluator:
    """Takes a text-to-logits predictor; `runner.predict` is called with raw text here
    rather than a numpy batch, since tokenization is model-specific — the caller's runner
    wraps its own tokenizer."""

    def evaluate(
        self, runner: ModelRunnerProtocol, loader: Iterable[Any], max_samples: int
    ) -> EvalResult:
        labels: list[int] = []
        predictions: list[int] = []
        for text, label in loader:
            if len(labels) >= max_samples:
                break
            logits = np.asarray(runner.predict(text)).reshape(-1)
            predictions.append(int(np.argmax(logits)))
            labels.append(int(label))

        if not labels:
            raise ValueError("no samples were available to evaluate")
        correct = sum(1 for actual, pred in zip(labels, predictions, strict=True) if actual == pred)
        accuracy = correct / len(labels)
        macro_f1 = _macro_f1(labels, predictions)
        return EvalResult(
            metric_name="Accuracy",
            value=accuracy,
            unit="%",
            samples_used=len(labels),
            extra={"macro_f1": macro_f1},
        )


__all__ = ["TextClassificationEvaluator"]
