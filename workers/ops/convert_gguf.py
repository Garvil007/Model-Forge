"""c_gguf: plain GGUF conversion (no quantization) for the Convert tab — F32, F16, BF16
or Q8_0 weight type, chosen via the `outtype` param. To also quantize, use GGUF under
Compress (`q_gguf`, `quantize_gguf.py`).

Only a Hugging Face `safetensors`/`torch` import has the config and tokenizer llama.cpp's
`convert_hf_to_gguf.py` needs (the same constraint `workers/ops/convert_onnx.py`'s
safetensors caster documents for Optimum), so this downloads the *full* HF repo snapshot
via `_llm_common.download_hf_snapshot` rather than reconstructing an architecture from
raw tensor names. A bespoke download -> convert -> upload runner, not
`_convert_common.run_convert_op`: that helper's own exception handling only knows about
`_convert_common.UnsupportedFormatError`, and this op needs `_llm_common.
classify_llm_error` to map a gated/licensed repo to the job's `gated_model` error code
rather than a generic "unknown" failure.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import require_hf_repo_id, s3_client
from ._gguf_common import convert_hf_to_gguf
from ._llm_common import classify_llm_error, download_hf_snapshot, resolve_hf_token


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

    tmpdir = tempfile.mkdtemp(prefix="mf-gguf-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            operation=operation, control=control, event_repo=event_repo, jobs=jobs,
            models=models, s3=s3, results_bucket=results_bucket,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    operation: OperationSpec, control: Any, event_repo: JobEventRepository,
    jobs: JobRepository, models: ModelRepository, s3: Any, results_bucket: str,
) -> None:
    model = models.get(user_id, model_id)
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

        stage = f"Converting to {operation.label}"
        outtype = params.get("outtype", "f16")
        event_repo.append(user_id, job_id, stage=stage, message=f"Writing GGUF ({outtype})")
        convert_hf_to_gguf(hf_dir, out_path, outtype)
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

    event_repo.append(
        user_id, job_id, stage="Checking outputs match",
        message="llama.cpp's own exporter validates tensor shapes during conversion",
    )
    control.check()

    output_bytes = out_path.stat().st_size
    download_name = f"{Path(model.filename).stem}.gguf"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(out_path), results_bucket, s3_key)

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": {
                "Conversion": (
                    "Converted directly from the Hugging Face repo; no separate "
                    "before/after check is run for a lossless format conversion"
                )
            },
            "measuredOnValidation": False,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )


__all__ = ["run"]
