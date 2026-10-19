"""mAP50-95 for detection.

Uses a pure-Python, IoU-matching, VOC2012-style interpolated-AP calculation rather than
`pycocotools.cocoeval.COCOeval`. `pycocotools` is now a base dependency (added to both
worker image lock files and `workers/pyproject.toml`) for other callers, but swapping this
evaluator onto `COCOeval` itself needs its own in-memory COCO-JSON construction and a
dedicated test pass against known reference numbers — left as a follow-up rather than
risking an unverified metric swap. The implementation below is covered by this module's
own tests on tiny synthetic boxes; treat it as directionally correct, not COCO-official.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from .base import EvalResult, ModelRunnerProtocol

Prediction = tuple[int, float, float, float, float, float]  # class_id, confidence, x1,y1,x2,y2
GroundTruthBox = tuple[int, float, float, float, float]  # class_id, x1,y1,x2,y2

_IOU_THRESHOLDS = tuple(round(0.5 + 0.05 * i, 2) for i in range(10))  # 0.50 .. 0.95


Box4 = tuple[float, float, float, float]


def _iou(box_a: Box4, box_b: Box4) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def _average_precision(recalls: list[float], precisions: list[float]) -> float:
    """VOC2012-style all-points interpolated average precision."""
    padded_recalls = [0.0, *recalls, 1.0]
    padded_precisions = [0.0, *precisions, 0.0]
    for i in range(len(padded_precisions) - 2, -1, -1):
        padded_precisions[i] = max(padded_precisions[i], padded_precisions[i + 1])
    return sum(
        (padded_recalls[i] - padded_recalls[i - 1]) * padded_precisions[i]
        for i in range(1, len(padded_recalls))
    )


def _ap_for_class_at_threshold(
    predictions: list[tuple[int, Prediction]],
    ground_truths: dict[int, list[GroundTruthBox]],
    class_id: int,
    iou_threshold: float,
) -> float | None:
    class_predictions = sorted(
        (p for p in predictions if p[1][0] == class_id), key=lambda p: p[1][1], reverse=True
    )
    total_gt = sum(1 for boxes in ground_truths.values() for box in boxes if box[0] == class_id)
    if total_gt == 0:
        return None

    matched: dict[int, set[int]] = {image_idx: set() for image_idx in ground_truths}
    true_positives, false_positives = [], []
    for image_idx, (cls, _confidence, x1, y1, x2, y2) in class_predictions:
        candidates = [
            (idx, box) for idx, box in enumerate(ground_truths.get(image_idx, [])) if box[0] == cls
        ]
        best_iou, best_idx = 0.0, -1
        for idx, box in candidates:
            if idx in matched[image_idx]:
                continue
            iou = _iou((x1, y1, x2, y2), box[1:])
            if iou > best_iou:
                best_iou, best_idx = iou, idx
        if best_iou >= iou_threshold and best_idx >= 0:
            matched[image_idx].add(best_idx)
            true_positives.append(1)
            false_positives.append(0)
        else:
            true_positives.append(0)
            false_positives.append(1)

    cumulative_tp = np.cumsum(true_positives)
    cumulative_fp = np.cumsum(false_positives)
    precisions = (cumulative_tp / np.maximum(cumulative_tp + cumulative_fp, 1)).tolist()
    recalls = (cumulative_tp / total_gt).tolist()
    return _average_precision(recalls, precisions)


def compute_map(
    predictions_by_image: dict[int, list[Prediction]],
    ground_truth_by_image: dict[int, list[GroundTruthBox]],
    *,
    iou_thresholds: tuple[float, ...] = _IOU_THRESHOLDS,
) -> float:
    """mAP averaged over `iou_thresholds` (default 0.50:0.05:0.95) and over classes."""
    flat_predictions = [
        (image_idx, prediction)
        for image_idx, predictions in predictions_by_image.items()
        for prediction in predictions
    ]
    class_ids = {box[0] for boxes in ground_truth_by_image.values() for box in boxes}
    if not class_ids:
        return 0.0

    per_threshold_maps = []
    for threshold in iou_thresholds:
        aps = [
            _ap_for_class_at_threshold(flat_predictions, ground_truth_by_image, class_id, threshold)
            for class_id in class_ids
        ]
        valid_aps = [ap for ap in aps if ap is not None]
        per_threshold_maps.append(sum(valid_aps) / len(valid_aps) if valid_aps else 0.0)
    return sum(per_threshold_maps) / len(per_threshold_maps)


class DetectionMapEvaluator:
    """`runner.predict(image)` must return `list[Prediction]` for a single image."""

    def evaluate(
        self, runner: ModelRunnerProtocol, loader: Iterable[Any], max_samples: int
    ) -> EvalResult:
        predictions_by_image: dict[int, list[Prediction]] = {}
        ground_truth_by_image: dict[int, list[GroundTruthBox]] = {}
        samples_used = 0
        for image, boxes in loader:
            if samples_used >= max_samples:
                break
            predictions_by_image[samples_used] = list(runner.predict(image))
            ground_truth_by_image[samples_used] = list(boxes)
            samples_used += 1

        if samples_used == 0:
            raise ValueError("no samples were available to evaluate")
        value = compute_map(predictions_by_image, ground_truth_by_image)
        return EvalResult(metric_name="mAP50-95", value=value, unit="", samples_used=samples_used)


__all__ = ["DetectionMapEvaluator", "compute_map"]
