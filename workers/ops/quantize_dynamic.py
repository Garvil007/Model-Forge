"""q_int8_dyn: ONNX Runtime dynamic int8 weight quantization.

Downloads the model from S3, quantizes it, measures a cheap output-similarity metric, uploads
the result, and writes the job's terminal status. This op owns its own `JobEvent`s and its own
success/failure `JobRecord.update_progress` call — the runner only handles cross-cutting stop
conditions (cancel/timeout/spot-interruption) via `control.check()`, called between stages.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository
from onnxruntime.quantization import QuantType, quantize_dynamic

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

_NUMPY_DTYPE_BY_ONNX_ELEM_TYPE = {
    1: np.float32,
    2: np.uint8,
    3: np.int8,
    6: np.int32,
    7: np.int64,
    10: np.float16,
    11: np.float64,
}


def _s3_client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def _download_name_for(filename: str) -> str:
    path = Path(filename)
    return f"{path.stem}.int8{path.suffix or '.onnx'}"


def _synthetic_input_for(session: onnxruntime.InferenceSession) -> dict[str, np.ndarray] | None:
    """Build one random input per model input, or None if shapes are too unusual to guess."""
    feeds: dict[str, np.ndarray] = {}
    rng = np.random.default_rng(0)
    for model_input in session.get_inputs():
        shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in model_input.shape]
        if not shape:
            shape = [1]
        dtype_name = model_input.type
        dtype = np.float32 if "float" in dtype_name else np.int64
        if dtype == np.float32:
            feeds[model_input.name] = rng.standard_normal(shape).astype(dtype)
        else:
            feeds[model_input.name] = rng.integers(0, 2, size=shape).astype(dtype)
    return feeds


def _measure_similarity(original_path: str, quantized_path: str) -> dict[str, str]:
    try:
        original_session = onnxruntime.InferenceSession(original_path)
        quantized_session = onnxruntime.InferenceSession(quantized_path)
        feeds = _synthetic_input_for(original_session)
        if feeds is None:
            return {"Output similarity": "not measured (unsupported input shape)"}
        original_out = original_session.run(None, feeds)[0].astype(np.float64).flatten()
        quantized_out = quantized_session.run(None, feeds)[0].astype(np.float64).flatten()
        denom = (np.linalg.norm(original_out) * np.linalg.norm(quantized_out)) or 1.0
        similarity = float(np.dot(original_out, quantized_out) / denom)
        return {"Output similarity": f"{similarity:.4f}"}
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return {"Output similarity": "not measured (comparison failed)"}


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
    s3_client: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client if s3_client is not None else _s3_client()
    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")

    tmpdir = tempfile.mkdtemp(prefix="mf-quantize-")
    try:
        _run_in_tempdir(
            tmpdir,
            user_id=user_id,
            job_id=job_id,
            model_id=model_id,
            jobs=jobs,
            models=models,
            s3=s3,
            uploads_bucket=uploads_bucket,
            results_bucket=results_bucket,
            control=control,
            event_repo=event_repo,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: str,
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    jobs: JobRepository,
    models: ModelRepository,
    s3: Any,
    uploads_bucket: str,
    results_bucket: str,
    control: Any,
    event_repo: JobEventRepository,
) -> None:
    model = models.get(user_id, model_id)
    local_in = str(Path(tmpdir) / "input.onnx")
    local_out = str(Path(tmpdir) / "output.onnx")

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, local_in)
    control.check()

    event_repo.append(
        user_id, job_id, stage="Quantizing weights", message="Running dynamic int8 quantization"
    )
    try:
        quantize_dynamic(model_input=local_in, model_output=local_out, weight_type=QuantType.QInt8)
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify onnxruntime failures for the UI
        message = str(error)
        lowered = message.lower()
        code = "unsupported_operator" if "support" in lowered or "op" in lowered else "unknown"
        jobs.update_progress(
            user_id,
            job_id,
            status="failed",
            progress_percent=50,
            error={"code": code, "message": message},
        )
        return
    control.check()

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy", message="Comparing outputs before/after"
    )
    metrics = _measure_similarity(local_in, local_out)
    control.check()

    output_bytes = os.path.getsize(local_out)
    download_name = _download_name_for(model.filename)
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(local_out, results_bucket, s3_key)

    jobs.update_progress(
        user_id,
        job_id,
        status="succeeded",
        progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": metrics,
            "measuredOnValidation": False,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )
