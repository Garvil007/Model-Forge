"""core.evaluators.topk: top-1/top-k accuracy."""

from __future__ import annotations

import numpy as np

from core.evaluators.topk import TopKAccuracyEvaluator


class _AlwaysPredictsClass0:
    def predict(self, batch: np.ndarray) -> np.ndarray:
        return np.array([[10.0, 0.0, 0.0]])


class _FixedLogitsRunner:
    def __init__(self, logits: list[float]) -> None:
        self._logits = logits

    def predict(self, batch: np.ndarray) -> np.ndarray:
        return np.array([self._logits])


def test_top1_accuracy_with_known_answer() -> None:
    # 10 samples, 6 labeled class 0 -> runner always predicts class 0 -> accuracy == 0.6
    labels = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1]
    loader = [(np.zeros(3), label) for label in labels]

    result = TopKAccuracyEvaluator(k=1).evaluate(_AlwaysPredictsClass0(), loader, max_samples=10)

    assert result.value == 0.6
    assert result.samples_used == 10
    assert result.metric_name == "Top-1 accuracy"


def test_top5_counts_label_within_top_five_logits() -> None:
    # label 2 ranks 3rd highest -> within top-5 but not top-1
    loader = [(np.zeros(1), 2)]
    runner = _FixedLogitsRunner([5.0, 4.0, 3.0, 2.0, 1.0, 0.0])

    result = TopKAccuracyEvaluator(k=5).evaluate(runner, loader, max_samples=1)

    assert result.value == 1.0
    assert result.metric_name == "Top-5 accuracy"


def test_top1_accuracy_zero_when_label_never_predicted() -> None:
    loader = [(np.zeros(1), 1), (np.zeros(1), 1)]

    result = TopKAccuracyEvaluator(k=1).evaluate(_AlwaysPredictsClass0(), loader, max_samples=10)

    assert result.value == 0.0


def test_max_samples_caps_evaluation() -> None:
    loader = [(np.zeros(1), 0) for _ in range(10)]

    result = TopKAccuracyEvaluator(k=1).evaluate(_AlwaysPredictsClass0(), loader, max_samples=3)

    assert result.samples_used == 3


def test_empty_loader_raises_value_error() -> None:
    import pytest

    with pytest.raises(ValueError):
        TopKAccuracyEvaluator(k=1).evaluate(_AlwaysPredictsClass0(), [], max_samples=5)
