"""core.evaluators.map_eval: pure-Python IoU-matching mAP50-95 fallback."""

from __future__ import annotations

import numpy as np
import pytest

from core.evaluators.map_eval import DetectionMapEvaluator, compute_map


def test_perfect_prediction_gives_map_of_one() -> None:
    predictions = {0: [(1, 0.9, 10.0, 10.0, 20.0, 20.0)]}
    ground_truth = {0: [(1, 10.0, 10.0, 20.0, 20.0)]}

    result = compute_map(predictions, ground_truth)

    assert result == pytest.approx(1.0)


def test_no_predictions_gives_map_of_zero() -> None:
    predictions: dict[int, list] = {0: []}
    ground_truth = {0: [(1, 10.0, 10.0, 20.0, 20.0)]}

    result = compute_map(predictions, ground_truth)

    assert result == pytest.approx(0.0)


def test_wrong_class_prediction_does_not_count_as_match() -> None:
    predictions = {0: [(2, 0.9, 10.0, 10.0, 20.0, 20.0)]}
    ground_truth = {0: [(1, 10.0, 10.0, 20.0, 20.0)]}

    result = compute_map(predictions, ground_truth)

    assert result == pytest.approx(0.0)


def test_no_ground_truth_boxes_gives_map_of_zero() -> None:
    result = compute_map({0: []}, {0: []})

    assert result == 0.0


def test_evaluator_runs_against_a_fake_detector_runner() -> None:
    class _PerfectDetector:
        def predict(self, image: np.ndarray) -> list:
            return [(1, 0.95, 10.0, 10.0, 20.0, 20.0)]

    loader = [(np.zeros((32, 32, 3), dtype=np.uint8), [(1, 10.0, 10.0, 20.0, 20.0)])]

    result = DetectionMapEvaluator().evaluate(_PerfectDetector(), loader, max_samples=5)

    assert result.value == pytest.approx(1.0)
    assert result.metric_name == "mAP50-95"
    assert result.samples_used == 1


def test_evaluator_raises_value_error_on_empty_loader() -> None:
    class _NoopDetector:
        def predict(self, image: np.ndarray) -> list:
            return []

    with pytest.raises(ValueError):
        DetectionMapEvaluator().evaluate(_NoopDetector(), [], max_samples=5)
