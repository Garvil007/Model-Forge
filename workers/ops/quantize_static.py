"""q_int8_static: INT8 *static* (calibrated) quantization — weights and activations both in
8-bit, with activation ranges picked from real sample inputs (the `calib` dataset param)
rather than guessed at inference time like `q_int8_dyn`.

- ONNX: `onnxruntime.quantization.quantize_static` fed by a `CalibrationDataReader` wrapping
  `core.datasets.calibration.CalibrationLoader`. QDQ format (`QuantFormat.QDQ` — inserts
  explicit QuantizeLinear/DequantizeLinear pairs, portable across runtimes, vs the fused
  `QOperator` format). Weights `QInt8`, activations `QUInt8` (the ORT-recommended default
  pairing for QDQ: symmetric signed weights, asymmetric unsigned activations). `per_channel`
  and the range-estimation `method` (minmax/entropy/percentile) come straight from the job's
  params, matching `packages/catalog/src/modelforge_catalog/methods.py`'s `q_int8_static`
  param spec.
- Keras -> TFLite: `tf.lite.TFLiteConverter` with a `representative_dataset` generator
  wrapping the same `CalibrationLoader`, `target_spec.supported_ops` restricted to
  `TFLITE_BUILTINS_INT8`, and both `inference_input_type`/`inference_output_type` set to
  `tf.int8` (signed, matching ONNX's `QInt8` weight convention above — picked for consistency
  across this op's output formats, not because TFLite prefers one over `uint8`).
- TorchScript: per the confirmed design, auto-exported to ONNX first
  (`torch.onnx.export`, using the calibration data's own sample shape as the dummy input —
  this op has no other source of the model's expected input shape), then quantized via the
  ONNX path above. A bare PyTorch `torch` (state_dict) source is refused the same way
  `quantize_dynamic.py` refuses it: no architecture to trace/export. An export failure for any
  other reason (unsupported op, dynamic control flow, ...) is also reported as
  `UnsupportedFormatError` rather than crashing uninformatively.

Downloads the model and the calibration dataset from S3, quantizes, measures accuracy via
`core.evaluation.evaluate_or_fallback` (real validation-dataset metrics when the model has one
configured, else the same best-effort output-similarity fallback `quantize_dynamic.py` uses),
uploads the result, and writes the job's terminal status — mirroring `quantize_dynamic.py`'s
structure throughout. Calls `control.check()` between stages (download / calibrate / quantize /
evaluate / upload), matching the calibration-stage insertion in
`packages/catalog/src/modelforge_catalog/job_stages.py` for `q_int8_static`.
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
from modelforge_catalog.validation import PreprocessSpec
from modelforge_db.records import ModelRecord
from modelforge_db.repositories.datasets import DatasetRepository
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core import evaluation
from core.datasets.calibration import CalibrationLoader
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError
from core.model_runner import create_runner
from core.similarity import compare_runs

_DEFAULT_SUFFIX = {"onnx": ".onnx", "torchscript": ".pt", "keras": ".h5"}
_CALIB_METHOD_NAMES = {"minmax": "MinMax", "entropy": "Entropy", "percentile": "Percentile"}
_NOT_MEASURED = "not measured"


class UnsupportedFormatError(Exception):
    """Raised when this op has no INT8-static path for the model's format."""


def _not_measured(reason: str) -> dict[str, str]:
    value = f"{_NOT_MEASURED} ({reason})"
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
    return f"{path.stem}.int8static{extension or path.suffix or '.bin'}"


def _calibration_loader(
    calib_path: Path, extract_dir: Path, preprocess: PreprocessSpec, max_samples: int, control: Any
) -> CalibrationLoader:
    return CalibrationLoader(
        calib_path, extract_dir, preprocess, max_samples=max_samples, control=control
    )


# --------------------------------------------------------------------------------- ONNX


class _OnnxCalibrationDataReader:
    """Wraps a `CalibrationLoader` as an `onnxruntime.quantization.CalibrationDataReader`."""

    def __init__(self, loader: CalibrationLoader, input_name: str) -> None:
        self._loader = loader
        self._input_name = input_name
        self._iterator = iter(loader)

    def get_next(self) -> dict[str, np.ndarray] | None:
        sample = next(self._iterator, None)
        if sample is None:
            return None
        return {self._input_name: np.asarray(sample, dtype=np.float32)[np.newaxis, ...]}

    def rewind(self) -> None:
        self._iterator = iter(self._loader)


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


def _quantize_onnx_static(
    path_in: Path, path_out: Path, calib_loader: CalibrationLoader, params: dict[str, Any]
) -> None:
    import onnxruntime
    from onnxruntime.quantization import CalibrationMethod, QuantFormat, QuantType, quantize_static

    session = onnxruntime.InferenceSession(str(path_in))
    input_name = session.get_inputs()[0].name
    reader = _OnnxCalibrationDataReader(calib_loader, input_name)
    method_name = _CALIB_METHOD_NAMES.get(params.get("method", "minmax"), "MinMax")

    quantize_static(
        model_input=str(path_in),
        model_output=str(path_out),
        calibration_data_reader=reader,
        quant_format=QuantFormat.QDQ,
        per_channel=bool(params.get("per_channel", True)),
        weight_type=QuantType.QInt8,
        activation_type=QuantType.QUInt8,
        calibrate_method=getattr(CalibrationMethod, method_name),
    )


def _onnx_fallback_metrics(path_in: Path, path_out: Path) -> dict[str, str]:
    import onnxruntime

    original_session = onnxruntime.InferenceSession(str(path_in))
    quantized_session = onnxruntime.InferenceSession(str(path_out))
    feeds = _onnx_synthetic_input(original_session)
    if feeds is None:
        return _not_measured("unsupported input shape")
    return compare_runs(
        lambda f: original_session.run(None, f), lambda f: quantized_session.run(None, f), feeds
    )


def _onnx_runner_factory(path_in: Path, path_out: Path) -> tuple[Any, Any]:
    return create_runner("onnx", path_in), create_runner("onnx", path_out)


# ------------------------------------------------------------------------------ PyTorch


def _first_calibration_sample_shape(calib_loader: CalibrationLoader) -> tuple[int, ...]:
    for sample in calib_loader:
        return (1, *np.asarray(sample).shape)
    raise UnsupportedFormatError("calibration dataset has no samples to infer an input shape from")


def _export_torchscript_to_onnx(
    path_in: Path, onnx_path: Path, calib_loader: CalibrationLoader
) -> None:
    import torch

    sample_shape = _first_calibration_sample_shape(calib_loader)
    try:
        module = torch.jit.load(str(path_in), map_location="cpu")
        module.eval()
        dummy = torch.zeros(sample_shape, dtype=torch.float32)
        torch.onnx.export(
            module, (dummy,), str(onnx_path), input_names=["input"], output_names=["output"],
            dynamo=False,
        )
    except UnsupportedFormatError:
        raise
    except Exception as error:  # noqa: BLE001 — classify as an unsupported op, not a crash
        raise UnsupportedFormatError(
            f"could not export TorchScript module to ONNX: {error}"
        ) from error


def _export_torch_statedict_to_onnx(*_args: Any, **_kwargs: Any) -> None:
    raise UnsupportedFormatError(
        "INT8 static quantization needs a runnable module (TorchScript); a bare PyTorch "
        "state_dict has no architecture to export to ONNX"
    )


_TORCH_EXPORTERS: dict[str, Callable[[Path, Path, CalibrationLoader], None]] = {
    "torchscript": _export_torchscript_to_onnx,
    "torch": _export_torch_statedict_to_onnx,
}


# -------------------------------------------------------------------------------- Keras


def _keras_input_shape(model: Any) -> tuple[int, ...] | None:
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return None
    return tuple(1 if d is None else d for d in shape)


def _quantize_keras_static(
    path_in: Path, path_out: Path, calib_loader: CalibrationLoader, _params: dict[str, Any]
) -> Any:
    import tensorflow as tf

    model = tf.keras.models.load_model(str(path_in), compile=False, safe_mode=True)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def _representative_dataset() -> Any:
        for sample in calib_loader:
            yield [np.asarray(sample, dtype=np.float32)[np.newaxis, ...]]

    converter.representative_dataset = _representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    path_out.write_bytes(converter.convert())
    return model


class _KerasRunner:
    """Adapts a loaded Keras model to `ModelRunnerProtocol` — `core.model_runner` has no Keras
    adapter since Keras is never this op's *result* format, only ever its source."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def predict(self, batch: np.ndarray) -> np.ndarray:
        return np.asarray(self._model.predict(batch, verbose=0))


def _keras_fallback_metrics(model: Any, path_out: Path) -> dict[str, str]:
    import tensorflow as tf

    input_shape = _keras_input_shape(model)
    if input_shape is None:
        return _not_measured("input shape unknown")

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

    return compare_runs(
        lambda f: [model.predict(sample, verbose=0)], _run_tflite, {"input": sample}
    )


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
    datasets_repo: DatasetRepository | None = None,
    s3_client: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    datasets = datasets_repo if datasets_repo is not None else DatasetRepository()
    s3 = s3_client if s3_client is not None else _s3_client()
    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")
    datasets_bucket = os.environ.get("MF_DATASETS_BUCKET", "mf-datasets")

    tmpdir = tempfile.mkdtemp(prefix="mf-quantize-static-")
    try:
        _run_in_tempdir(
            tmpdir,
            user_id=user_id,
            job_id=job_id,
            model_id=model_id,
            params=params,
            jobs=jobs,
            models=models,
            datasets=datasets,
            s3=s3,
            uploads_bucket=uploads_bucket,
            results_bucket=results_bucket,
            datasets_bucket=datasets_bucket,
            control=control,
            event_repo=event_repo,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _download_calibration_dataset(
    *, tmpdir: str, params: dict[str, Any], datasets: DatasetRepository, s3: Any,
    datasets_bucket: str, user_id: str,
) -> Path:
    dataset_id = params.get("calib")
    if not dataset_id:
        raise UnsupportedFormatError("the 'calib' dataset param is required for q_int8_static")
    dataset_record = datasets.get(user_id, dataset_id)
    calib_path = Path(tmpdir) / f"calib{Path(dataset_record.filename).suffix}"
    s3.download_file(datasets_bucket, dataset_record.s3_key, str(calib_path))
    return calib_path


def _quantize(
    *, model: ModelRecord, params: dict[str, Any], local_in: Path, local_out: Path,
    calib_loader: CalibrationLoader,
) -> tuple[Path, Path, Any]:
    """Returns `(onnx_in, onnx_out, keras_model_or_none)` — for onnx/torch* sources `onnx_in`
    is the file actually quantized against (the original, or a TorchScript export of it);
    `keras_model_or_none` is the loaded Keras model when the source is Keras, for the fallback
    comparison path, else `None`."""
    if model.format == "onnx":
        _quantize_onnx_static(local_in, local_out, calib_loader, params)
        return local_in, local_out, None
    if model.format in _TORCH_EXPORTERS:
        exported_onnx = local_in.with_suffix(".exported.onnx")
        _TORCH_EXPORTERS[model.format](local_in, exported_onnx, calib_loader)
        _quantize_onnx_static(exported_onnx, local_out, calib_loader, params)
        return exported_onnx, local_out, None
    if model.format == "keras":
        keras_model = _quantize_keras_static(local_in, local_out, calib_loader, params)
        return local_in, local_out, keras_model
    raise UnsupportedFormatError(f"no INT8-static path for format {model.format!r}")


def _build_fallback(
    model: ModelRecord, onnx_in: Path, onnx_out: Path, keras_model: Any
) -> Callable[[], dict[str, str]]:
    if model.format == "keras":
        return lambda: _keras_fallback_metrics(keras_model, onnx_out)
    return lambda: _onnx_fallback_metrics(onnx_in, onnx_out)


def _build_runner_factory(
    model: ModelRecord, onnx_in: Path, onnx_out: Path, keras_model: Any
) -> Callable[[], tuple[Any, Any]] | None:
    if model.format == "keras":
        return lambda: (_KerasRunner(keras_model), create_runner("tflite", onnx_out))
    return lambda: _onnx_runner_factory(onnx_in, onnx_out)


def _run_in_tempdir(
    tmpdir: str,
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    jobs: JobRepository,
    models: ModelRepository,
    datasets: DatasetRepository,
    s3: Any,
    uploads_bucket: str,
    results_bucket: str,
    datasets_bucket: str,
    control: Any,
    event_repo: JobEventRepository,
) -> None:
    model = models.get(user_id, model_id)
    suffix = _suffix_for(model.format, model.filename)
    local_in = Path(tmpdir) / f"input{suffix}"
    out_name = "output.tflite" if model.format == "keras" else "output.onnx"
    local_out = Path(tmpdir) / out_name

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    event_repo.append(
        user_id, job_id, stage="Running calibration data", message="Downloading calibration data"
    )
    try:
        calib_path = _download_calibration_dataset(
            tmpdir=tmpdir, params=params, datasets=datasets, s3=s3,
            datasets_bucket=datasets_bucket, user_id=user_id,
        )
        preprocess = evaluation.build_preprocess_spec(model.details or {})
        calib_loader = _calibration_loader(
            calib_path, Path(tmpdir) / "calib_extracted", preprocess,
            int(params.get("samples", 300)), control,
        )
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify calibration-data failures for the UI
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=25,
            error={"code": "invalid_calibration_data", "message": str(error)},
        )
        return
    control.check()

    event_repo.append(
        user_id, job_id, stage="Quantizing weights", message="Running calibrated int8 quantization"
    )
    try:
        onnx_in, onnx_out, keras_model = _quantize(
            model=model, params=params, local_in=local_in, local_out=local_out,
            calib_loader=calib_loader,
        )
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify framework failures for the UI
        message = str(error)
        lowered = message.lower()
        code = (
            "unsupported_operator"
            if isinstance(error, UnsupportedFormatError) or "support" in lowered or "op" in lowered
            else "unknown"
        )
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=50,
            error={"code": code, "message": message},
        )
        return
    control.check()

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy", message="Comparing outputs before/after"
    )
    metrics, measured_on_validation, evaluation_detail = evaluation.evaluate_or_fallback(
        model_record=model,
        control=control,
        fallback=_build_fallback(model, onnx_in, onnx_out, keras_model),
        runner_factory=_build_runner_factory(model, onnx_in, onnx_out, keras_model),
        s3=s3,
        datasets_repo=datasets,
        validation_bucket=datasets_bucket,
    )
    control.check()

    output_bytes = local_out.stat().st_size
    download_name = _download_name_for(model.filename, local_out.suffix)
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(local_out), results_bucket, s3_key)

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
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


__all__ = ["run", "UnsupportedFormatError"]
