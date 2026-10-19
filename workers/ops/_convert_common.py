"""Shared plumbing for the Convert-tab worker ops (`convert_*.py`): S3 download/upload, the
"not measured" fallback shape, Hugging Face repo-id lookup for a safetensors model (reusing
the `details["repoId"]` field `workers/ops/import_hf.py` already writes rather than
inventing a new one), and a generic download -> convert -> validate -> upload ->
job-status runner shared by every convert op so each `convert_*.py` file only supplies its
own per-source-format caster functions.

Every caster is handed a `ConvertContext` and returns a metrics dict (via `not_measured`
or `core.similarity.compare_runs`/`compare_arrays`), writing its converted model to
`context.local_out` — a single file for most targets, or a directory for SavedModel and
OpenVINO IR (`output_is_directory=True`), which this module zips before upload since a job
result is always one S3 object.

Security note, consistent with every other worker op in this package: a bare PyTorch `torch`
(state_dict) source has no architecture to convert anywhere and is refused by every
`convert_*.py` caster map (it's simply absent as a key), which this runner reports as a clean
`unsupported_operator` rather than a crash — the same precedent `workers/ops/quantize_dynamic.py`
already set for `q_int8_dyn`.

The YOLO caster in each `convert_*.py` module loads an untrusted upload through
`ultralytics.YOLO(path)`, which internally unpickles a checkpoint via `torch.load`. Ultralytics'
own default (`ultralytics.utils.patches.torch_load`) passes `weights_only=False` unless told
otherwise — i.e. unrestricted pickle, same class of RCE surface as `torch.jit.load`/
`keras.load_model` (see `fp_cast.py`'s note). Ultralytics 8.4+ ships an opt-in restricted loader
(`ultralytics.nn.tasks._SafeLoad`, `torch_safe_load(..., safe_only=True)`) that does
`torch.load(weights_only=True)` against an allow-list of its own known classes, but it is OFF by
default (gated by the `ULTRALYTICS_SAFE_LOAD` env var, read once into a module-level constant at
import time). `load_yolo_safely` below forces that restricted path by flipping the already-
imported `ultralytics.nn.tasks.SAFE_LOAD` module attribute for the duration of the call, so
`YOLO(path)` never falls back to unrestricted unpickling. Verified empirically against a real
`yolo11n.yaml`-built checkpoint saved via `YOLO.save()` and reloaded under the restricted path
(see `workers/tests/test_convert_onnx.py::test_yolo_source_exports_to_onnx` and the analogous
tflite/torchscript/openvino tests) — it loads successfully; Ultralytics' allow-list already
covers its own `DetectionModel`/`nn.Module` class graph. If a checkpoint references a pickled
type outside that allow-list, the restricted loader raises `TypeError` instead of silently
falling back, and `load_yolo_safely` turns that into a clean `UnsupportedFormatError` rather than
retrying unrestricted.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.records import ModelRecord
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.convert_chain import ChainHopError
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

_NOT_MEASURED = "not measured"

_SUFFIX_FOR_FORMAT = {
    "onnx": ".onnx",
    "torch": ".pt",
    "torchscript": ".pt",
    "keras": ".h5",
    "safetensors": ".safetensors",
    "yolo": ".pt",
}


class UnsupportedFormatError(Exception):
    """Raised when a convert op has no caster for the model's source format, or a required
    precondition (e.g. an HF repo id on a safetensors model) is missing."""


def not_measured(reason: str) -> dict[str, str]:
    value = f"{_NOT_MEASURED} ({reason})"
    return {"Output similarity": value, "Max difference": value, "Top-1 agreement": value}


def s3_client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def parse_shape(
    shape_text: str | None, default: tuple[int, ...] = (1, 3, 224, 224)
) -> tuple[int, ...]:
    """Parses the `shape` param ("1,3,224,224") into a tuple of ints, falling back to a
    default image-like shape if the text is missing or malformed — a convert job should
    degrade to a reasonable guess here, not fail outright over a cosmetic input slip."""
    if not shape_text:
        return default
    try:
        dims = tuple(int(part.strip()) for part in shape_text.split(","))
    except ValueError:
        return default
    return dims or default


def require_hf_repo_id(model: ModelRecord) -> str:
    """A bare safetensors file has no architecture (the same constraint `workers/ops/
    fp_cast.py` documents for a bare PyTorch state_dict): exporting it needs the Hugging
    Face repo id + config that `workers/ops/import_hf.py` already stores on
    `model.details["repoId"]` when the model came from an HF import, so Optimum can
    re-resolve the real `transformers` model class and its tokenizer/generation config —
    reusing the uploaded safetensors bytes directly would mean this worker hand-rolling its
    own architecture reconstruction from raw tensor names, which is out of scope."""
    repo_id = (model.details or {}).get("repoId")
    if not repo_id:
        raise UnsupportedFormatError(
            "exporting a safetensors model needs its Hugging Face repo id — import it via "
            "'Import from Hugging Face' rather than a raw file upload so the architecture "
            "and config are known"
        )
    return str(repo_id)


def load_yolo_safely(path: Path) -> Any:
    """Load an untrusted YOLO checkpoint via Ultralytics' restricted `weights_only=True`
    loader, never Ultralytics' own unrestricted default (see module docstring).

    Flips the already-imported `ultralytics.nn.tasks.SAFE_LOAD` flag on for the duration of
    this call — the env-var gate (`ULTRALYTICS_SAFE_LOAD`) is read once at import time into
    that module constant, so setting the env var here would be a no-op once `ultralytics`
    has already been imported anywhere in the process. Restored in a `finally` rather than
    left on, since flipping it process-wide for the rest of the job would also force the
    restricted path on unrelated Ultralytics calls (e.g. `yolo.export(...)` below, which has
    no need for it and whose own internal behavior this module doesn't own).

    Raises `UnsupportedFormatError` — refuses cleanly, like `fp_cast.py` refuses a bare
    state_dict — if the checkpoint references a pickled type outside Ultralytics' safe-load
    allow-list, rather than silently retrying with unrestricted unpickling.
    """
    from ultralytics import YOLO
    from ultralytics.nn import tasks as ultralytics_tasks

    previous_safe_load = ultralytics_tasks.SAFE_LOAD
    ultralytics_tasks.SAFE_LOAD = True
    try:
        return YOLO(str(path))
    except TypeError as error:
        raise UnsupportedFormatError(
            "YOLO checkpoint references pickled types outside Ultralytics' safe-load "
            f"allow-list; refusing rather than falling back to unrestricted unpickling: {error}"
        ) from error
    finally:
        ultralytics_tasks.SAFE_LOAD = previous_safe_load


def zip_directory(directory: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in directory.rglob("*"):
            if member.is_file():
                archive.write(member, member.relative_to(directory))


def input_suffix(model_format: str, filename: str) -> str:
    return Path(filename).suffix or _SUFFIX_FOR_FORMAT.get(model_format, "")


class ConvertContext:
    """Everything a per-format caster function needs, passed as one object so every
    `convert_*.py` caster shares a uniform signature regardless of how many of these
    fields it actually uses."""

    def __init__(
        self,
        *,
        model: ModelRecord,
        local_in: Path,
        local_out: Path,
        tmpdir: Path,
        params: dict[str, Any],
        control: Any,
        event_repo: JobEventRepository,
        user_id: str,
        job_id: str,
        stage: str,
    ) -> None:
        self.model = model
        self.local_in = local_in
        self.local_out = local_out
        self.tmpdir = tmpdir
        self.params = params
        self.control = control
        self.event_repo = event_repo
        self.user_id = user_id
        self.job_id = job_id
        self.stage = stage


Caster = Callable[[ConvertContext], dict[str, str]]


def run_convert_op(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    casters: dict[str, Caster],
    output_is_directory: bool = False,
    output_suffix: str | None = None,
    tmp_prefix: str = "mf-convert-",
    job_repo: JobRepository | None = None,
    models_repo: ModelRepository | None = None,
    s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")

    tmpdir = tempfile.mkdtemp(prefix=tmp_prefix)
    try:
        _run_in_tempdir(
            Path(tmpdir),
            user_id=user_id,
            job_id=job_id,
            model_id=model_id,
            params=params,
            operation=operation,
            control=control,
            event_repo=event_repo,
            casters=casters,
            output_is_directory=output_is_directory,
            output_suffix=output_suffix,
            jobs=jobs,
            models=models,
            s3=s3,
            uploads_bucket=uploads_bucket,
            results_bucket=results_bucket,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _classify_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, ChainHopError):
        message = str(error)
        is_unsupported = isinstance(error.original, UnsupportedFormatError)
        return ("unsupported_operator" if is_unsupported else "unknown"), message
    code = "unsupported_operator" if isinstance(error, UnsupportedFormatError) else "unknown"
    return code, str(error)


def _run_in_tempdir(
    tmpdir: Path,
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    casters: dict[str, Caster],
    output_is_directory: bool,
    output_suffix: str | None,
    jobs: JobRepository,
    models: ModelRepository,
    s3: Any,
    uploads_bucket: str,
    results_bucket: str,
) -> None:
    model = models.get(user_id, model_id)
    stage = f"Converting to {operation.label}"
    local_in = tmpdir / f"input{input_suffix(model.format, model.filename)}"

    event_repo.append(
        user_id, job_id, stage="Loading model", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    suffix = output_suffix if output_suffix is not None else f".{operation.target_format}"
    local_out = tmpdir / ("output" if output_is_directory else f"output{suffix}")
    if output_is_directory:
        local_out.mkdir(parents=True, exist_ok=True)

    caster = casters.get(model.format)
    context = ConvertContext(
        model=model, local_in=local_in, local_out=local_out, tmpdir=tmpdir, params=params,
        control=control, event_repo=event_repo, user_id=user_id, job_id=job_id, stage=stage,
    )
    try:
        if caster is None:
            raise UnsupportedFormatError(
                f"no {operation.label} conversion for format {model.format!r}"
            )
        event_repo.append(user_id, job_id, stage=stage, message=f"Converting from {model.format}")
        metrics = caster(context)
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify framework failures for the UI
        code, message = _classify_error(error)
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=50,
            error={"code": code, "message": message},
        )
        return
    control.check()

    event_repo.append(
        user_id, job_id, stage="Checking outputs match", message="Comparing outputs before/after"
    )
    control.check()

    if output_is_directory:
        upload_path = tmpdir / "output.zip"
        zip_directory(local_out, upload_path)
        download_suffix = ".zip"
    else:
        upload_path = local_out
        download_suffix = local_out.suffix

    output_bytes = upload_path.stat().st_size
    download_name = f"{Path(model.filename).stem}.{operation.target_format}{download_suffix}"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(upload_path), results_bucket, s3_key)

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": metrics,
            "measuredOnValidation": False,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )


__all__ = [
    "Caster",
    "ConvertContext",
    "UnsupportedFormatError",
    "input_suffix",
    "load_yolo_safely",
    "not_measured",
    "parse_shape",
    "require_hf_repo_id",
    "run_convert_op",
    "s3_client",
    "zip_directory",
]
