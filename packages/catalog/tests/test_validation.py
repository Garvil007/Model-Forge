"""Tests for modelforge_catalog.validation — task-type metadata and metric formatting."""

from __future__ import annotations

from typing import get_args

from modelforge_catalog.validation import (
    TASK_TYPE_INFO,
    PreprocessSpec,
    TaskType,
    format_metric,
)


def test_task_type_literal_has_exactly_four_values() -> None:
    assert set(get_args(TaskType)) == {"image_cls", "detection", "text_cls", "lm"}


def test_preprocess_spec_defaults_match_vision_conventions() -> None:
    spec = PreprocessSpec()
    assert spec.input_size == 224
    assert spec.mean == (0.485, 0.456, 0.406)
    assert spec.std == (0.229, 0.224, 0.225)
    assert spec.channel_order == "RGB"
    assert spec.layout == "NCHW"


def test_preprocess_spec_is_frozen() -> None:
    spec = PreprocessSpec()
    try:
        spec.input_size = 320  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("PreprocessSpec should be immutable")


def test_task_type_info_covers_every_task_type() -> None:
    assert set(TASK_TYPE_INFO) == set(get_args(TaskType))


def test_image_cls_task_type_info() -> None:
    info = TASK_TYPE_INFO["image_cls"]
    assert info.accept == ".zip"
    assert info.metric_label == "Top-1 accuracy"
    assert info.lower_is_better is False


def test_detection_task_type_info() -> None:
    info = TASK_TYPE_INFO["detection"]
    assert info.accept == ".zip"
    assert info.metric_label == "mAP50-95"
    assert info.lower_is_better is False


def test_text_cls_task_type_info() -> None:
    info = TASK_TYPE_INFO["text_cls"]
    assert info.accept == ".csv,.jsonl"
    assert info.metric_label == "Accuracy"
    assert info.lower_is_better is False


def test_lm_task_type_info_is_lower_is_better() -> None:
    info = TASK_TYPE_INFO["lm"]
    assert info.accept == ".txt,.jsonl"
    assert info.metric_label == "Perplexity"
    assert info.lower_is_better is True


def test_format_metric_higher_is_better_matches_result_panel_convention() -> None:
    # Matches ResultPanel.stories.tsx `RealValidationAccuracy` / mocks/handlers.ts convention:
    # the new value leads, with the old value parenthesized as "(was X)".
    assert format_metric(76.1, 75.8, "%") == "75.8% (was 76.1%)"


def test_format_metric_lower_is_better_matches_perplexity_story_convention() -> None:
    # Matches ResultPanel.stories.tsx `PerplexityForLlm` / ui-prototype.html showResult()
    # phrasing for lower-is-better metrics: "before, ... after (lower is better)".
    assert (
        format_metric(9.75, 9.91, "", lower_is_better=True)
        == "9.75 before, 9.91 after (lower is better)"
    )


def test_format_metric_handles_integer_valued_floats_cleanly() -> None:
    assert format_metric(100.0, 90.0, "%") == "90% (was 100%)"
