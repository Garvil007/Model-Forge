"""evaluate_or_fallback: shared accuracy-measurement layer for quantization/conversion ops.

Prefers running the model's validation dataset (configured via `PATCH /models/{id}/validation`,
see `details.validationDatasetId`/`taskType`/`preprocess` on `ModelRecord`) through the right
`core.evaluators` evaluator for its `taskType`, reporting a real before/after metric. Falls back
to `core.similarity.compare_runs`'s random-input output-similarity check when there's no
validation data configured, or degrades to that same fallback (with an added `"note"` key
explaining why) if anything about the validation-dataset path fails — a validation-dataset
problem (bad format, missing tokenizer, dataset download failure, ...) must never fail the job.

Returned shape: `(metrics, measured_on_validation, evaluation)`
- `metrics`: `dict[str, str]`, display-ready — the same shape `compare_runs` already returns,
  so callers/the UI don't need to branch on it. On a fallback this is exactly the caller's
  `fallback()` dict, optionally with an extra `"note"` key when it's a *degraded* fallback
  (validation data was configured but could not be used).
- `measured_on_validation`: `True` only when a real validation-dataset metric was computed.
- `evaluation`: `None` on any fallback; otherwise a dict with `taskType`, `metricName`,
  `before`, `after`, `unit`, `samplesUsed`, `datasetId` for job-result consumers that want the
  raw numbers behind the formatted `metrics` string.

Capped at `max_samples` (default 1000, matching `q_int8_static`'s `samples` param ceiling).
Cooperative cancellation/timeout is preserved: the dataset loaders themselves call
`control.check()` every ~50-200 samples (see `core.datasets.*`), and this module also calls it
once per download/evaluation stage.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.validation import TASK_TYPE_INFO, PreprocessSpec, format_metric
from modelforge_db.records import ModelRecord

from .datasets.detection import DetectionLoader
from .datasets.imagefolder import ImageFolderLoader
from .datasets.lm import LanguageModelingLoader
from .datasets.text import TextClassificationLoader
from .evaluators.cls_f1 import TextClassificationEvaluator
from .evaluators.map_eval import DetectionMapEvaluator
from .evaluators.perplexity import PerplexityEvaluator
from .evaluators.topk import TopKAccuracyEvaluator
from .exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

_MAX_VALIDATION_SAMPLES = 1000
_PREPROCESS_FIELDS = frozenset(PreprocessSpec.__dataclass_fields__)

RunnerFactory = Callable[[], tuple[Any, Any]]


class EvaluationError(Exception):
    """Raised for a validation-dataset problem (bad format, missing tokenizer, etc). Always
    caught by `evaluate_or_fallback`, which turns it into a graceful fallback instead of
    letting it fail the job."""


def build_preprocess_spec(details: dict[str, Any]) -> PreprocessSpec:
    """Build a `PreprocessSpec` from a `ModelRecord.details["preprocess"]` dict (JSON-decoded
    from DynamoDB, so `mean`/`std` arrive as lists rather than tuples)."""
    raw = dict(details.get("preprocess") or {})
    for key in ("mean", "std"):
        if raw.get(key) is not None:
            raw[key] = tuple(float(value) for value in raw[key])
    return PreprocessSpec(**{k: v for k, v in raw.items() if k in _PREPROCESS_FIELDS})


def _build_tokenizer(model_record: ModelRecord) -> Any:
    """Loads a tokenizer for text_cls/lm evaluation. `transformers` is imported lazily so this
    module still imports fine on a worker image that doesn't have it installed (not yet a
    declared dependency anywhere — see Phase 4 task notes) — it only errors when a text/LM
    evaluation is actually attempted."""
    repo_id = (model_record.details or {}).get("repoId")
    if not repo_id:
        raise EvaluationError(
            "text/LM accuracy evaluation needs a tokenizer source, but this model has no "
            "Hugging Face repo id (details.repoId) to load one from"
        )
    try:
        from transformers import AutoTokenizer
    except ImportError as error:
        raise EvaluationError(
            "transformers is not installed in this worker image; cannot load a tokenizer "
            "for text/LM accuracy evaluation"
        ) from error
    return AutoTokenizer.from_pretrained(repo_id)


class _TextClassificationRunner:
    """Adapts a `ModelRunnerProtocol` + tokenizer so `TextClassificationEvaluator` (which calls
    `runner.predict(text: str)`) can run against a real model, whose runner otherwise only
    accepts numpy batches."""

    def __init__(self, inner: Any, tokenizer: Any) -> None:
        self._inner = inner
        self._tokenizer = tokenizer

    def predict(self, text: str) -> Any:
        token_ids = self._tokenizer.encode(text)
        batch = np.asarray(token_ids, dtype=np.int64)[np.newaxis, :]
        return self._inner.predict(batch)


def _build_loader_and_evaluator(
    *,
    task_type: str,
    local_path: Path,
    extract_dir: Path,
    preprocess: PreprocessSpec,
    max_samples: int,
    control: Any,
    tokenizer_factory: Callable[[], Any],
) -> tuple[Any, Any]:
    loader: Any
    if task_type == "image_cls":
        loader = ImageFolderLoader(
            local_path, extract_dir, preprocess, max_samples=max_samples, control=control
        )
        return loader, TopKAccuracyEvaluator(k=1)
    if task_type == "detection":
        loader = DetectionLoader(
            local_path, extract_dir, preprocess, max_samples=max_samples, control=control
        )
        return loader, DetectionMapEvaluator()
    if task_type == "text_cls":
        loader = TextClassificationLoader(local_path, max_samples=max_samples, control=control)
        return loader, TextClassificationEvaluator()
    if task_type == "lm":
        loader = LanguageModelingLoader(local_path, max_samples=max_samples, control=control)
        return loader, PerplexityEvaluator(tokenizer_factory())
    raise EvaluationError(f"unsupported task type {task_type!r}")


def _wrap_runners_for_task(
    task_type: str, orig_runner: Any, new_runner: Any, tokenizer_factory: Callable[[], Any]
) -> tuple[Any, Any]:
    if task_type != "text_cls":
        return orig_runner, new_runner
    tokenizer = tokenizer_factory()
    return (
        _TextClassificationRunner(orig_runner, tokenizer),
        _TextClassificationRunner(new_runner, tokenizer),
    )


def _evaluate_on_validation_dataset(
    *,
    model_record: ModelRecord,
    dataset_id: str,
    task_type: str,
    details: dict[str, Any],
    control: Any,
    runner_factory: RunnerFactory,
    s3: Any,
    datasets_repo: Any,
    validation_bucket: str | None,
    max_samples: int,
) -> tuple[dict[str, str], bool, dict[str, Any]]:
    if s3 is None or datasets_repo is None or not validation_bucket:
        raise EvaluationError(
            "validation-dataset evaluation needs s3, datasets_repo, and validation_bucket"
        )
    if task_type not in TASK_TYPE_INFO:
        raise EvaluationError(f"unsupported task type {task_type!r}")

    dataset_record = datasets_repo.get(model_record.user_id, dataset_id)
    tmpdir = tempfile.mkdtemp(prefix="mf-validation-")
    try:
        local_path = Path(tmpdir) / f"dataset{Path(dataset_record.filename).suffix}"
        s3.download_file(validation_bucket, dataset_record.s3_key, str(local_path))
        control.check()

        preprocess = build_preprocess_spec(details)
        extract_dir = Path(tmpdir) / "extracted"
        tokenizer_cache: list[Any] = []

        def _tokenizer_factory() -> Any:
            if not tokenizer_cache:
                tokenizer_cache.append(_build_tokenizer(model_record))
            return tokenizer_cache[0]

        loader, evaluator = _build_loader_and_evaluator(
            task_type=task_type,
            local_path=local_path,
            extract_dir=extract_dir,
            preprocess=preprocess,
            max_samples=max_samples,
            control=control,
            tokenizer_factory=_tokenizer_factory,
        )

        orig_runner, new_runner = runner_factory()
        orig_runner, new_runner = _wrap_runners_for_task(
            task_type, orig_runner, new_runner, _tokenizer_factory
        )

        before = evaluator.evaluate(orig_runner, loader, max_samples)
        control.check()
        after = evaluator.evaluate(new_runner, loader, max_samples)
        control.check()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    info = TASK_TYPE_INFO[task_type]
    metrics = {
        info.metric_label: format_metric(
            before.value, after.value, after.unit, lower_is_better=info.lower_is_better
        )
    }
    evaluation = {
        "taskType": task_type,
        "metricName": info.metric_label,
        "before": before.value,
        "after": after.value,
        "unit": after.unit,
        "samplesUsed": after.samples_used,
        "datasetId": dataset_id,
    }
    return metrics, True, evaluation


def evaluate_or_fallback(
    *,
    model_record: ModelRecord,
    control: Any,
    fallback: Callable[[], dict[str, str]],
    runner_factory: RunnerFactory | None = None,
    s3: Any = None,
    datasets_repo: Any = None,
    validation_bucket: str | None = None,
    max_samples: int = _MAX_VALIDATION_SAMPLES,
) -> tuple[dict[str, str], bool, dict[str, Any] | None]:
    """Measure accuracy before/after for a quantization/conversion op.

    `fallback` is a zero-arg callable the op builds itself (typically wrapping
    `core.similarity.compare_runs` with its own per-format synthetic-input logic) — used as-is
    when the model has no validation dataset configured, and used again (with a `"note"`
    explaining why) if the validation-dataset path raises anything.

    `runner_factory`, if given, lazily builds `(orig_runner, new_runner)` — two
    `ModelRunnerProtocol` adapters over the original and result model files — only when a real
    validation-dataset evaluation is actually attempted, since building them (loading sessions,
    interpreters, etc.) isn't free. Pass `None` for an op that doesn't support real
    validation-dataset evaluation yet; it always falls back in that case.
    """
    details = model_record.details or {}
    dataset_id = details.get("validationDatasetId")
    task_type = details.get("taskType")
    if not dataset_id or not task_type or runner_factory is None:
        return fallback(), False, None

    try:
        return _evaluate_on_validation_dataset(
            model_record=model_record,
            dataset_id=dataset_id,
            task_type=task_type,
            details=details,
            control=control,
            runner_factory=runner_factory,
            s3=s3,
            datasets_repo=datasets_repo,
            validation_bucket=validation_bucket,
            max_samples=max_samples,
        )
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — a validation-dataset problem must not fail the job
        degraded = dict(fallback())
        degraded["note"] = f"real accuracy not measured: {error}"
        return degraded, False, None


__all__ = ["EvaluationError", "build_preprocess_spec", "evaluate_or_fallback"]
