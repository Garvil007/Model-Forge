"""Model validation task types, preprocessing defaults, and metric formatting.

Shared by apps/api (validates the `PATCH /models/{id}/validation` request body and the
params of ops like `q_int8_static` that need a validation/calibration dataset) and by
workers (which run the validation pass and format before/after metrics for the job result).

Pure data/typing/formatting only — no numpy/torch/onnx imports — so apps/api can import this
module for request validation without pulling in any model-loading code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TaskType = Literal["image_cls", "detection", "text_cls", "lm"]
ChannelOrder = Literal["RGB", "BGR"]
Layout = Literal["NCHW", "NHWC"]


@dataclass(frozen=True, slots=True)
class PreprocessSpec:
    """Preprocessing applied before running validation inputs through a model.

    Defaults are the standard ImageNet-style vision preprocessing (as used by resnet50 etc.
    in docs/ui-prototype.html's SAMPLES); callers fill in only the fields a submitted
    `preprocess` dict omits, so a vision task with an empty dict still gets sane values.
    Non-vision task types (text_cls, lm) ignore these fields entirely.
    """

    input_size: int | None = 224
    mean: tuple[float, ...] | None = (0.485, 0.456, 0.406)
    std: tuple[float, ...] | None = (0.229, 0.224, 0.225)
    channel_order: ChannelOrder = "RGB"
    layout: Layout = "NCHW"


@dataclass(frozen=True, slots=True)
class TaskTypeInfo:
    """Per-task-type metadata: accepted validation dataset uploads and metric naming."""

    accept: str
    metric_label: str
    lower_is_better: bool = False


TASK_TYPE_INFO: dict[TaskType, TaskTypeInfo] = {
    "image_cls": TaskTypeInfo(accept=".zip", metric_label="Top-1 accuracy"),
    "detection": TaskTypeInfo(accept=".zip", metric_label="mAP50-95"),
    "text_cls": TaskTypeInfo(accept=".csv,.jsonl", metric_label="Accuracy"),
    "lm": TaskTypeInfo(accept=".txt,.jsonl", metric_label="Perplexity", lower_is_better=True),
}


def _format_number(value: float) -> str:
    """Render a metric value the way the UI does: trim to 2 decimals, drop trailing zeros."""
    return f"{round(value, 2):g}"


def format_metric(before: float, after: float, unit: str, *, lower_is_better: bool = False) -> str:
    """Format a before/after metric value for the job result panel.

    Two display conventions exist in the codebase, and the choice between them depends on
    whether a smaller number is an improvement:
    - Higher-is-better metrics (accuracy, mAP) lead with the new value and parenthesize the
      old one, e.g. "75.8% (was 76.1%)" (ResultPanel.stories.tsx `RealValidationAccuracy`,
      mocks/handlers.ts `advanceJob`).
    - Lower-is-better metrics (perplexity) would read backwards under that convention, so
      they instead read left-to-right as "before, ... after (lower is better)"
      (ResultPanel.stories.tsx `PerplexityForLlm`, docs/ui-prototype.html `showResult()`).

    `lower_is_better` picks the phrasing explicitly rather than inferring it from the metric
    name, since callers already know this from `TaskTypeInfo.lower_is_better`.
    """
    before_str = _format_number(before)
    after_str = _format_number(after)
    if lower_is_better:
        return f"{before_str} before, {after_str} after (lower is better)"
    return f"{after_str}{unit} (was {before_str}{unit})"


__all__ = [
    "TaskType",
    "ChannelOrder",
    "Layout",
    "PreprocessSpec",
    "TaskTypeInfo",
    "TASK_TYPE_INFO",
    "format_metric",
]
