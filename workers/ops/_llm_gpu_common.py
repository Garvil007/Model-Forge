"""Shared GPU-LLM quantization runner for `q_gptq`/`q_awq`/`q_nf4` (`workers/ops/
quantize_gptq.py`, `quantize_awq.py`, `quantize_nf4.py`): download the full Hugging Face
repo, load it with Transformers, measure perplexity before, hand off to the op's own
`quantize_fn` to produce a quantized model loadable by both Transformers and vLLM
(`save_pretrained` writes a `config.json`/`quantization_config` either library reads),
reload the result fresh and measure perplexity after, then upload.

CPU test mode: `device` defaults to `os.environ.get("MF_LLM_DEVICE", "cuda")`, so the
real `gpu-base` image runs on CUDA but a test can set `MF_LLM_DEVICE=cpu` to exercise the
exact same code path — download, load, quantize, reload, measure — against a tiny
random Llama config with no GPU and no network (a test monkeypatches
`huggingface_hub.snapshot_download` to copy a local directory already shaped like an HF
snapshot, the same "fake the network edge, run everything else for real" shape as the
existing worker tests' S3 fakes).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_catalog.validation import format_metric
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.evaluators.perplexity import PerplexityEvaluator
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import require_hf_repo_id, s3_client, zip_directory
from ._llm_common import (
    classify_llm_error,
    download_hf_snapshot,
    resolve_calibration_dataset,
    resolve_hf_token,
)

_PERPLEXITY_MAX_SAMPLES = 8
_PERPLEXITY_WINDOW = 256
_PERPLEXITY_STRIDE = 128

# quantize_fn(model, tokenizer, repo_dir, local_out, params, device, calibration_texts) -> None
# Must leave a complete, loadable Transformers model + tokenizer under `local_out`.
QuantizeFn = Callable[[Any, Any, Path, Path, dict[str, Any], str, list[str]], None]


class _HfCausalLmRunner:
    """Adapts a loaded `transformers` causal-LM for `core.evaluators.perplexity.
    PerplexityEvaluator`, which calls `.predict(batch) -> logits` (see
    `core.evaluators.base.ModelRunnerProtocol`) with a `[1, seq_len]` int64 token batch."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def predict(self, batch: np.ndarray) -> np.ndarray:
        import torch

        with torch.no_grad():
            input_ids = torch.as_tensor(np.asarray(batch), dtype=torch.long).to(self._model.device)
            logits = self._model(input_ids).logits
        return logits.float().cpu().numpy()


def resolve_device() -> str:
    return os.environ.get("MF_LLM_DEVICE", "cuda")


def _measure_perplexity(model: Any, tokenizer: Any, calibration_texts: list[str]) -> float:
    evaluator = PerplexityEvaluator(
        tokenizer, window_size=_PERPLEXITY_WINDOW, stride=_PERPLEXITY_STRIDE
    )
    result = evaluator.evaluate(
        _HfCausalLmRunner(model), calibration_texts, _PERPLEXITY_MAX_SAMPLES
    )
    return result.value


def run_llm_gpu_quantize(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    quantize_fn: QuantizeFn,
    needs_calibration: bool,
    tag: str,
    job_repo: JobRepository | None = None,
    models_repo: ModelRepository | None = None,
    s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")
    device = resolve_device()

    tmpdir = tempfile.mkdtemp(prefix="mf-llm-gpu-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            results_bucket=results_bucket, quantize_fn=quantize_fn,
            needs_calibration=needs_calibration, tag=tag, device=device,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, results_bucket: str, quantize_fn: QuantizeFn, needs_calibration: bool, tag: str,
    device: str,
) -> None:
    model_record = models.get(user_id, model_id)
    local_out = tmpdir / "output"
    local_out.mkdir(parents=True, exist_ok=True)
    before_ppl: float | None = None
    after_ppl: float | None = None
    calibration_texts: list[str] = []

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading Hugging Face repo"
    )
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        repo_id = require_hf_repo_id(model_record)
        token = resolve_hf_token(user_id)
        repo_dir = tmpdir / "hf_repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        download_hf_snapshot(repo_id, token, repo_dir)
        control.check()

        tokenizer = AutoTokenizer.from_pretrained(repo_dir)
        model = AutoModelForCausalLM.from_pretrained(
            repo_dir, torch_dtype=torch.float32, device_map=device
        )
        calibration_texts = resolve_calibration_dataset(
            params if "dataset" in params else {"dataset": "wikitext2"}
        )

        event_repo.append(
            user_id, job_id, stage="Loading model", message="Measuring baseline perplexity"
        )
        before_ppl = _measure_perplexity(model, tokenizer, calibration_texts)
        control.check()

        if needs_calibration:
            event_repo.append(
                user_id, job_id, stage="Running calibration data",
                message="Running calibration data through the model",
            )
            control.check()

        event_repo.append(user_id, job_id, stage="Quantizing weights", message="Quantizing weights")
        quantize_fn(model, tokenizer, repo_dir, local_out, params, device, calibration_texts)
        del model
        control.check()

        event_repo.append(
            user_id, job_id, stage="Measuring accuracy", message="Measuring perplexity after"
        )
        quantized_model = AutoModelForCausalLM.from_pretrained(local_out, device_map=device)
        after_ppl = _measure_perplexity(quantized_model, tokenizer, calibration_texts)
        del quantized_model
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classified below for the UI
        code, message = classify_llm_error(error)
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=50,
            error={"code": code, "message": message},
        )
        return
    control.check()

    upload_path = tmpdir / "output.zip"
    zip_directory(local_out, upload_path)
    output_bytes = upload_path.stat().st_size
    download_name = f"{Path(model_record.filename).stem}_{tag}.zip"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(upload_path), results_bucket, s3_key)

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": {
                "Perplexity": format_metric(before_ppl, after_ppl, "", lower_is_better=True)
            },
            "measuredOnValidation": True,
            "evaluation": {
                "taskType": "lm",
                "metricName": "Perplexity",
                "before": before_ppl,
                "after": after_ppl,
                "unit": "",
                "samplesUsed": len(calibration_texts),
                "datasetId": None,
            },
            "speedNote": None,
            "s3Key": s3_key,
        },
    )


__all__ = ["QuantizeFn", "resolve_device", "run_llm_gpu_quantize"]
