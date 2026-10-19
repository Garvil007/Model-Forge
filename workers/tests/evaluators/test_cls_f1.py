"""core.evaluators.cls_f1: accuracy + macro-F1 for text classification."""

from __future__ import annotations

import numpy as np
import pytest

from core.evaluators.cls_f1 import TextClassificationEvaluator


class _LabelToLogitsRunner:
    """Predicts whatever class index the test wires up for each text, in order."""

    def __init__(self, predictions: list[int], num_classes: int = 3) -> None:
        self._predictions = iter(predictions)
        self._num_classes = num_classes

    def predict(self, _text: str) -> np.ndarray:
        predicted = next(self._predictions)
        logits = [0.0] * self._num_classes
        logits[predicted] = 10.0
        return np.array(logits)


def test_perfect_predictions_give_accuracy_and_f1_of_one() -> None:
    labels = [0, 1, 2, 0]
    loader = [("t", label) for label in labels]
    runner = _LabelToLogitsRunner(predictions=labels)

    result = TextClassificationEvaluator().evaluate(runner, loader, max_samples=10)

    assert result.value == 1.0
    assert result.extra["macro_f1"] == 1.0
    assert result.samples_used == 4


def test_known_accuracy_with_some_misclassifications() -> None:
    labels = [0, 0, 1, 1]
    predictions = [0, 1, 1, 1]  # 3/4 correct
    loader = [("t", label) for label in labels]
    runner = _LabelToLogitsRunner(predictions=predictions)

    result = TextClassificationEvaluator().evaluate(runner, loader, max_samples=10)

    assert result.value == 0.75


def test_max_samples_caps_evaluation() -> None:
    labels = [0, 1, 0, 1, 0]
    loader = [("t", label) for label in labels]
    runner = _LabelToLogitsRunner(predictions=[0, 0, 0, 0, 0])

    result = TextClassificationEvaluator().evaluate(runner, loader, max_samples=2)

    assert result.samples_used == 2


def test_empty_loader_raises_value_error() -> None:
    with pytest.raises(ValueError):
        TextClassificationEvaluator().evaluate(_LabelToLogitsRunner([]), [], max_samples=5)
