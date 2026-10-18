"""q_fp16 / q_bf16: cast a model's weights to half precision.

One worker handles both operations — they differ only in target dtype (fp16 vs bf16) and,
per source format, in which caster can run at all (BF16 only makes sense for PyTorch and
safetensors here; see `packages/catalog/src/modelforge_catalog/methods.py`'s
`source_formats`). Each caster is format-specific because "cast weights to half precision"
means something different per framework:

- ONNX: `onnxconverter_common.float16.convert_float_to_float16`, keeping graph I/O at
  float32 so a float32 synthetic input works unchanged against both the original and the
  result — enables a real output-similarity run via `core.similarity`.
- Keras (`.h5` or `.keras`): rewrites float32 HDF5 datasets to float16 directly (needs only
  `h5py`, a base dependency — no TensorFlow required to produce the result). The
  output-similarity run still needs TensorFlow to execute the model, so it degrades to "not
  measured" when TensorFlow isn't installed in this image (see `workers/images/cpu-tf`).
- PyTorch `torch` (state_dict): recursively casts every floating tensor in the loaded
  object. No architecture is available from a bare state_dict, so there's nothing to run
  for a similarity comparison.
- PyTorch `torchscript`: `.half()` on the loaded `ScriptModule`. Runnable in principle, but
  a serialized TorchScript graph doesn't reliably carry a static input shape to replay
  after a save/load round-trip, so this also reports "not measured" rather than guessing.
- `safetensors`: raw named tensors, no architecture — same "not measured" story as a bare
  PyTorch state_dict, cast via `safetensors.torch` so both fp16 and bf16 share one path.

Every caster refuses an already-sub-32-bit source model itself (defense in depth — the API
already enforces `OperationSpec.required_bit_width` before a job is ever created).

Security note: `tf.keras.models.load_model` and `torch.jit.load` both deserialize a
user-uploaded file — the Keras calls pass `safe_mode=True, compile=False` to reject
Lambda-layer/arbitrary-callable configs and skip optimizer deserialization, and the
PyTorch state_dict path uses `torch.load(..., weights_only=True)`; TorchScript's loader
isn't a generic pickle stream, but still parses untrusted bytes. Full isolation (no IAM
credentials in this process, per-object pre-signed URLs instead of a credentialed boto3
client, seccomp/gVisor) is a worker-sandboxing concern for `infra/`, not something this op
module can provide on its own — tracked in `docs/PROGRESS.md`'s Day 11 gaps.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError
from core.similarity import compare_runs

_MIN_SOURCE_BIT_WIDTH = 32
_DEFAULT_SUFFIX = {
    "onnx": ".onnx",
    "torch": ".pt",
    "torchscript": ".pt",
    "keras": ".h5",
    "safetensors": ".safetensors",
}


class UnsupportedFormatError(Exception):
    """Raised when this op has no caster for the model's format, or the format/dtype
    combination isn't one the catalog actually offers (e.g. BF16 for ONNX)."""


def _not_measured(reason: str) -> dict[str, str]:
    value = f"not measured ({reason})"
    return {"Output similarity": value, "Max difference": value, "Top-1 agreement": value}


def _label_for(operation_id: str) -> str:
    return "fp16" if operation_id == "q_fp16" else "bf16"


def _suffix_for(model_format: str, filename: str) -> str:
    return Path(filename).suffix or _DEFAULT_SUFFIX.get(model_format, "")


def _download_name_for(filename: str, label: str) -> str:
    path = Path(filename)
    return f"{path.stem}.{label}{path.suffix}"


def _s3_client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


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


def _cast_onnx(path_in: Path, path_out: Path, label: str) -> dict[str, str]:
    if label != "fp16":
        raise UnsupportedFormatError("BF16 casting isn't offered for ONNX")
    import onnx
    import onnxruntime
    from onnxconverter_common import float16

    model = onnx.load(str(path_in))
    casted = float16.convert_float_to_float16(model, keep_io_types=True)
    onnx.save(casted, str(path_out))

    original_session = onnxruntime.InferenceSession(str(path_in))
    result_session = onnxruntime.InferenceSession(str(path_out))
    feeds = _onnx_synthetic_input(original_session)
    if feeds is None:
        return _not_measured("unsupported input shape")
    return compare_runs(
        lambda f: original_session.run(None, f),
        lambda f: result_session.run(None, f),
        feeds,
    )


# -------------------------------------------------------------------------------- Keras


def _halve_hdf5_floats(path: Path) -> None:
    with h5py.File(path, "r+") as handle:
        float_paths: list[str] = []
        handle.visititems(
            lambda name, obj: float_paths.append(name)
            if isinstance(obj, h5py.Dataset) and obj.dtype.kind == "f" and obj.dtype.itemsize > 2
            else None
        )
        for name in float_paths:
            dataset = handle[name]
            data = dataset[...].astype(np.float16)
            attrs = dict(dataset.attrs)
            parent_path, _, leaf = name.rpartition("/")
            parent = handle[parent_path] if parent_path else handle
            del handle[name]
            new_dataset = parent.create_dataset(leaf, data=data)
            for key, value in attrs.items():
                new_dataset.attrs[key] = value


def _keras_input_shape(model: Any) -> tuple[int, ...] | None:
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return None
    return tuple(1 if d is None else d for d in shape)


def _compare_keras_models(path_in: Path, path_out: Path) -> dict[str, str]:
    try:
        import tensorflow as tf
    except ImportError:
        return _not_measured("tensorflow unavailable for comparison")
    try:
        # safe_mode=True (Keras's default, passed explicitly) rejects Lambda layers and
        # other arbitrary-callable configs instead of executing them; compile=False skips
        # deserializing the optimizer/loss config, which has its own arbitrary-code history
        # (see the security-review note on this op's model entry).
        original = tf.keras.models.load_model(str(path_in), compile=False, safe_mode=True)
        result = tf.keras.models.load_model(str(path_out), compile=False, safe_mode=True)
        input_shape = _keras_input_shape(original)
        if input_shape is None:
            return _not_measured("input shape unknown")
        rng = np.random.default_rng(0)
        sample = rng.standard_normal(input_shape).astype(np.float32)
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return _not_measured("comparison failed")
    return compare_runs(
        lambda f: [original.predict(sample, verbose=0)],
        lambda f: [result.predict(sample, verbose=0)],
        {"input": sample},
    )


def _cast_keras(path_in: Path, path_out: Path, label: str) -> dict[str, str]:
    if label != "fp16":
        raise UnsupportedFormatError("BF16 casting isn't offered for Keras")
    if zipfile.is_zipfile(path_in):
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(path_in) as archive:
                archive.extractall(extract_dir)
            weights_path = Path(extract_dir) / "model.weights.h5"
            if not weights_path.exists():
                raise UnsupportedFormatError("no model.weights.h5 in .keras archive")
            _halve_hdf5_floats(weights_path)
            with zipfile.ZipFile(path_out, "w", zipfile.ZIP_DEFLATED) as archive:
                for member in Path(extract_dir).rglob("*"):
                    if member.is_file():
                        archive.write(member, member.relative_to(extract_dir))
    else:
        shutil.copyfile(path_in, path_out)
        _halve_hdf5_floats(path_out)
    return _compare_keras_models(path_in, path_out)


# -------------------------------------------------------------------------------- PyTorch


def _torch_dtype(label: str) -> Any:
    import torch

    return torch.float16 if label == "fp16" else torch.bfloat16


def _cast_tensor_tree(obj: Any, dtype: Any) -> Any:
    import torch

    if torch.is_tensor(obj):
        return obj.to(dtype) if torch.is_floating_point(obj) else obj
    if isinstance(obj, dict):
        return {key: _cast_tensor_tree(value, dtype) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        casted = [_cast_tensor_tree(value, dtype) for value in obj]
        return type(obj)(casted)
    return obj


def _cast_torch_statedict(path_in: Path, path_out: Path, label: str) -> dict[str, str]:
    import torch

    state = torch.load(str(path_in), map_location="cpu", weights_only=True)
    torch.save(_cast_tensor_tree(state, _torch_dtype(label)), str(path_out))
    return _not_measured("state dict has no architecture to run")


def _cast_torchscript(path_in: Path, path_out: Path, label: str) -> dict[str, str]:
    if label != "fp16":
        raise UnsupportedFormatError("BF16 casting isn't offered for TorchScript")
    import torch

    module = torch.jit.load(str(path_in), map_location="cpu")
    module.half()
    torch.jit.save(module, str(path_out))
    return _not_measured("a serialized TorchScript graph has no static input shape to replay")


def _cast_safetensors(path_in: Path, path_out: Path, label: str) -> dict[str, str]:
    import torch
    from safetensors.torch import load_file, save_file

    dtype = _torch_dtype(label)
    tensors = load_file(str(path_in))
    casted = {
        name: (tensor.to(dtype) if torch.is_floating_point(tensor) else tensor)
        for name, tensor in tensors.items()
    }
    save_file(casted, str(path_out))
    return _not_measured("raw tensors have no architecture to run")


_CASTERS: dict[str, Callable[[Path, Path, str], dict[str, str]]] = {
    "onnx": _cast_onnx,
    "keras": _cast_keras,
    "torch": _cast_torch_statedict,
    "torchscript": _cast_torchscript,
    "safetensors": _cast_safetensors,
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

    tmpdir = tempfile.mkdtemp(prefix="mf-fpcast-")
    try:
        _run_in_tempdir(
            tmpdir,
            user_id=user_id,
            job_id=job_id,
            model_id=model_id,
            operation=operation,
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
    operation: OperationSpec,
    jobs: JobRepository,
    models: ModelRepository,
    s3: Any,
    uploads_bucket: str,
    results_bucket: str,
    control: Any,
    event_repo: JobEventRepository,
) -> None:
    model = models.get(user_id, model_id)
    label = _label_for(operation.id)
    suffix = _suffix_for(model.format, model.filename)
    local_in = Path(tmpdir) / f"input{suffix}"
    local_out = Path(tmpdir) / f"output{suffix}"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    if model.bits is not None and model.bits < _MIN_SOURCE_BIT_WIDTH:
        jobs.update_progress(
            user_id,
            job_id,
            status="failed",
            progress_percent=10,
            error={
                "code": "unsupported_operator",
                "message": (
                    f"{label.upper()} needs a 32-bit source model; this model is already "
                    f"{model.bits:g}-bit"
                ),
            },
        )
        return

    event_repo.append(
        user_id, job_id, stage="Quantizing weights", message=f"Casting weights to {label.upper()}"
    )
    caster = _CASTERS.get(model.format)
    try:
        if caster is None:
            raise UnsupportedFormatError(f"no {label} caster for format {model.format!r}")
        metrics = caster(local_in, local_out, label)
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify framework failures for the UI
        code = "unsupported_operator" if isinstance(error, UnsupportedFormatError) else "unknown"
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=50,
            error={"code": code, "message": str(error)},
        )
        return
    control.check()

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy", message="Comparing outputs before/after"
    )
    control.check()

    output_bytes = local_out.stat().st_size
    download_name = _download_name_for(model.filename, label)
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
            "measuredOnValidation": False,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )
