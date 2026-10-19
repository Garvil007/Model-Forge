"""q_gguf: GGUF quantization via llama.cpp — downloads the full Hugging Face repo,
converts it to an F16 base GGUF, optionally builds an importance matrix from
calibration text (`llama-imatrix`), quantizes to the chosen block type (Q8_0, Q6_K,
Q5_K_M, Q4_K_M, Q3_K_M, Q2_K) with `llama-quantize`, and measures perplexity before
(the F16 base) and after (the quantized result) with `llama-perplexity` — all CPU work,
matching this op's `cpu-llm` worker image and `cpu` queue (`packages/catalog/src/
modelforge_catalog/methods.py`'s `q_gguf`).

Stage list matches `job_stages.py`'s `quantization` branch exactly: "Loading model",
then "Running calibration data" only when `imatrix` is set, then "Quantizing weights",
then "Measuring accuracy".
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_catalog.validation import format_metric
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import require_hf_repo_id, s3_client
from ._gguf_common import build_imatrix, convert_hf_to_gguf, measure_perplexity, quantize_gguf_file
from ._llm_common import (
    classify_llm_error,
    download_hf_snapshot,
    resolve_calibration_text,
    resolve_hf_token,
)

_PERPLEXITY_CHUNKS = 8


def run(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    job_repo: JobRepository | None = None,
    models_repo: ModelRepository | None = None,
    s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")

    tmpdir = tempfile.mkdtemp(prefix="mf-quantize-gguf-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            results_bucket=results_bucket,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, results_bucket: str,
) -> None:
    model = models.get(user_id, model_id)
    qtype = params.get("qtype", "Q4_K_M")
    use_imatrix = bool(params.get("imatrix", True))
    base_gguf = tmpdir / "base.gguf"
    out_path = tmpdir / "output.gguf"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading Hugging Face repo"
    )
    try:
        repo_id = require_hf_repo_id(model)
        token = resolve_hf_token(user_id)
        hf_dir = tmpdir / "hf_repo"
        hf_dir.mkdir(parents=True, exist_ok=True)
        download_hf_snapshot(repo_id, token, hf_dir)
        control.check()

        event_repo.append(
            user_id, job_id, stage="Loading model", message="Converting to an F16 base GGUF"
        )
        convert_hf_to_gguf(hf_dir, base_gguf, "f16")
        control.check()

        calibration_path = tmpdir / "calibration.txt"
        calibration_path.write_text(resolve_calibration_text(params), encoding="utf-8")

        imatrix_path: Path | None = None
        if use_imatrix:
            event_repo.append(
                user_id, job_id, stage="Running calibration data",
                message="Building an importance matrix",
            )
            imatrix_path = tmpdir / "imatrix.dat"
            build_imatrix(base_gguf, calibration_path, imatrix_path)
            control.check()

        event_repo.append(
            user_id, job_id, stage="Quantizing weights", message=f"Quantizing to {qtype}"
        )
        quantize_gguf_file(base_gguf, out_path, qtype, imatrix_path=imatrix_path)
        control.check()

        event_repo.append(
            user_id, job_id, stage="Measuring accuracy", message="Comparing perplexity before/after"
        )
        before_ppl = measure_perplexity(base_gguf, calibration_path, chunks=_PERPLEXITY_CHUNKS)
        after_ppl = measure_perplexity(out_path, calibration_path, chunks=_PERPLEXITY_CHUNKS)
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

    output_bytes = out_path.stat().st_size
    download_name = f"{Path(model.filename).stem}_{qtype}.gguf"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(out_path), results_bucket, s3_key)

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
                "samplesUsed": _PERPLEXITY_CHUNKS,
                "datasetId": None,
            },
            "speedNote": "runs on CPU with llama.cpp",
            "s3Key": s3_key,
        },
    )


__all__ = ["run"]
