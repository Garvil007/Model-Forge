"""q_int8_dyn: INT8 dynamic quantization, one tool per source format.

- ONNX: `onnxruntime.quantization.quantize_dynamic` (weights only, activations quantized on
  the fly at inference time — no calibration data needed).
- PyTorch `torchscript`: `torch.ao.quantization.quantize_jit.quantize_dynamic_jit` on the
  loaded `ScriptModule` — the graph-rewriting API, not `torch.quantization.quantize_dynamic`
  (which is a silent no-op here: it swaps modules by Python type, and a scripted module's
  children are `RecursiveScriptModule` wrappers, never `isinstance(..., nn.Linear)`).
  Verified against a reloaded graph showing real `quantized::linear_dynamic` nodes, not
  just a successful call. A bare PyTorch `torch` (state_dict) source has no architecture to
  quantize against, so it's refused with `unsupported_operator` rather than guessing one.
- Keras: `tf.lite.TFLiteConverter` with `optimizations=[tf.lite.Optimize.DEFAULT]` — this
  *is* "INT8 dynamic" for a Keras source; TensorFlow doesn't offer an in-place
  weights-only dynamic quantization the way ONNX Runtime and PyTorch do, so the standard
  tool is the TFLite converter, and the result format changes to `.tflite`.

Downloads the model from S3, quantizes it, measures the output-similarity metrics (see
`core.similarity`), uploads the result, and writes the job's terminal status. This op owns
its own `JobEvent`s and its own success/failure `JobRecord.update_progress` call — the
runner only handles cross-cutting stop conditions (cancel/timeout/spot-interruption) via
`control.check()`, called between stages.

Security note: `tf.keras.models.load_model` and `torch.jit.load` both deserialize a
user-uploaded file — the Keras call passes `safe_mode=True, compile=False` to reject
Lambda-layer/arbitrary-callable configs and skip optimizer deserialization. TorchScript's
loader isn't a generic pickle stream, but still parses untrusted bytes. Full isolation (no
IAM credentials in this process, per-object pre-signed URLs instead of a credentialed
boto3 client, seccomp/gVisor) is a worker-sandboxing concern for `infra/`, not something
this op module can provide on its own — tracked in `docs/PROGRESS.md`'s Day 11 gaps.
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
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core import evaluation
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError
from core.similarity import compare_runs

_DEFAULT_SUFFIX = {"onnx": ".onnx", "torchscript": ".pt", "keras": ".h5"}


class UnsupportedFormatError(Exception):
    """Raised when this op has no INT8-dynamic path for the model's format."""


def _not_measured(reason: str) -> dict[str, str]:
    value = f"not measured ({reason})"
    return {"Output similarity": value, "Max difference": value, "Top-1 agreement": value}


def _s3_client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def _suffix_for(model_format: str, filename: str) -> str:
    return Path(filename).suffix or _DEFAULT_SUFFIX.get(model_format, "")


def _download_name_for(filename: str, extension: str | None = None) -> str:
    path = Path(filename)
    return f"{path.stem}.int8{extension or path.suffix or '.bin'}"


# --------------------------------------------------------------------------------- ONNX


def _onnx_synthetic_input(session: Any) -> dict[str, np.ndarray] | None:
    rng = np.random.default_rng(0)
    feeds: dict[str, np.ndarray] = {}
    for model_input in session.get_inputs():
        shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in model_input.shape]
        if not shape:
            shape = [1]
        is_float = "float" in model_input.type
        dtype = np.float32 if is_float else np.int64
        feeds[model_input.name] = (
            rng.standard_normal(shape).astype(dtype)
            if is_float
            else rng.integers(0, 2, size=shape).astype(dtype)
        )
    return feeds or None


def _quantize_onnx(
    path_in: Path, path_out: Path
) -> tuple[Callable[[], dict[str, str]], str | None]:
    import onnxruntime
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        model_input=str(path_in), model_output=str(path_out), weight_type=QuantType.QInt8
    )

    original_session = onnxruntime.InferenceSession(str(path_in))
    result_session = onnxruntime.InferenceSession(str(path_out))

    def _fallback() -> dict[str, str]:
        feeds = _onnx_synthetic_input(original_session)
        if feeds is None:
            return _not_measured("unsupported input shape")
        return compare_runs(
            lambda f: original_session.run(None, f),
            lambda f: result_session.run(None, f),
            feeds,
        )

    return _fallback, None


# ------------------------------------------------------------------------------ PyTorch


def _quantize_torchscript(
    path_in: Path, path_out: Path
) -> tuple[Callable[[], dict[str, str]], str | None]:
    # `torch.quantization.quantize_dynamic` only swaps modules by Python type and is a
    # silent no-op on an already-scripted/traced graph (its children are
    # `RecursiveScriptModule` wrappers, never `isinstance(..., nn.Linear)`). The JIT-level
    # API below rewrites the graph itself (`aten::linear` -> `quantized::linear_dynamic`),
    # verified against a saved/reloaded traced module before relying on it here.
    import torch
    from torch.ao.quantization import per_channel_dynamic_qconfig
    from torch.ao.quantization.quantize_jit import quantize_dynamic_jit

    module = torch.jit.load(str(path_in), map_location="cpu")
    quantized = quantize_dynamic_jit(module, {"": per_channel_dynamic_qconfig})
    torch.jit.save(quantized, str(path_out))
    reason = "a serialized TorchScript graph has no static input shape to replay"
    return lambda: _not_measured(reason), None


def _quantize_torch_statedict(
    path_in: Path, path_out: Path
) -> tuple[Callable[[], dict[str, str]], str | None]:
    raise UnsupportedFormatError(
        "INT8 dynamic quantization needs a runnable module (TorchScript); a bare "
        "PyTorch state_dict has no architecture to quantize against"
    )


# -------------------------------------------------------------------------------- Keras


def _keras_input_shape(model: Any) -> tuple[int, ...] | None:
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return None
    return tuple(1 if d is None else d for d in shape)


def _quantize_keras(
    path_in: Path, path_out: Path
) -> tuple[Callable[[], dict[str, str]], str | None]:
    import tensorflow as tf

    # safe_mode=True rejects Lambda layers / arbitrary-callable configs instead of
    # executing them; compile=False skips the optimizer/loss config entirely.
    model = tf.keras.models.load_model(str(path_in), compile=False, safe_mode=True)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_bytes = converter.convert()
    path_out.write_bytes(tflite_bytes)

    input_shape = _keras_input_shape(model)
    if input_shape is None:
        return lambda: _not_measured("input shape unknown"), ".tflite"

    rng = np.random.default_rng(0)
    sample = rng.standard_normal(input_shape).astype(np.float32)
    interpreter = tf.lite.Interpreter(model_path=str(path_out))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]

    def _run_tflite(_feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        interpreter.set_tensor(input_details["index"], sample.astype(input_details["dtype"]))
        interpreter.invoke()
        return [interpreter.get_tensor(output_details["index"])]

    def _fallback() -> dict[str, str]:
        return compare_runs(
            lambda f: [model.predict(sample, verbose=0)], _run_tflite, {"input": sample}
        )

    return _fallback, ".tflite"


_QUANTIZERS: dict[str, Callable[[Path, Path], tuple[Callable[[], dict[str, str]], str | None]]] = {
    "onnx": _quantize_onnx,
    "torchscript": _quantize_torchscript,
    "torch": _quantize_torch_statedict,
    "keras": _quantize_keras,
}


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
    suffix = _suffix_for(model.format, model.filename)
    local_in = Path(tmpdir) / f"input{suffix}"
    local_out = Path(tmpdir) / f"output{suffix}"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    event_repo.append(
        user_id, job_id, stage="Quantizing weights", message="Running dynamic int8 quantization"
    )
    quantizer = _QUANTIZERS.get(model.format)
    try:
        if quantizer is None:
            raise UnsupportedFormatError(f"no INT8-dynamic path for format {model.format!r}")
        fallback_fn, output_extension = quantizer(local_in, local_out)
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify framework failures for the UI
        message = str(error)
        lowered = message.lower()
        code = (
            "unsupported_operator"
            if isinstance(error, UnsupportedFormatError)
            or "support" in lowered
            or "op" in lowered
            else "unknown"
        )
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
    metrics, measured_on_validation, evaluation_detail = evaluation.evaluate_or_fallback(
        model_record=model, control=control, fallback=fallback_fn, runner_factory=None,
    )
    control.check()

    output_bytes = local_out.stat().st_size
    download_name = _download_name_for(model.filename, output_extension)
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(local_out), results_bucket, s3_key)

    jobs.update_progress(
        user_id,
        job_id,
        status="succeeded",
        progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": metrics,
            "measuredOnValidation": measured_on_validation,
            "evaluation": evaluation_detail,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )
