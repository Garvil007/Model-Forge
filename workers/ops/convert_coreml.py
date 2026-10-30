"""c_coreml: convert a model to Core ML (an `.mlpackage` directory, zipped before upload
like `convert_savedmodel.py`'s SavedModel output).

- TorchScript: `coremltools.convert()` accepts an already-loaded `torch.jit.ScriptModule`
  directly, given a concrete `ct.TensorType` input shape — there is no architecture to infer
  one from, so this falls back to the job's `shape` param (`_convert_common.parse_shape`,
  same 224x224 RGB default every other shape-needing convert op uses) since `c_coreml` has
  no dedicated shape param of its own in the catalog.
- Keras: `coremltools.convert()` also accepts a loaded `tf.keras` model object directly
  (source inferred as `"tensorflow"`), same as `convert_openvino.py`'s Keras caster passing
  a model object straight to `openvino.convert_model()`.
- YOLO: Ultralytics' own exporter (`YOLO(path).export(format="coreml", half=...)`), which
  wraps `coremltools` itself — no need to call `ct.convert()` ourselves for this source.
  Ultralytics may emit either an `.mlpackage` directory or an `.mlmodel` file depending on
  version/options, so the result is copied into this op's output directory under its own
  name rather than assuming one shape (same "copy whatever the exporter actually wrote"
  approach as `convert_openvino.py`'s YOLO caster).

  Security note: `YOLO(path)` parses untrusted bytes via `torch.load`, a known pickle-RCE
  surface — see `_convert_common.load_yolo_safely`'s docstring for why this module forces
  Ultralytics' restricted `weights_only=True` loader instead of its unrestricted default.
- `torch` (bare PyTorch state_dict): refused, same as every other convert op — no
  architecture to trace, and this project never unpickles a full `nn.Module` from an
  untrusted upload to work around that (see `workers/ops/fp_cast.py`).
- Precision param (`fp32`/`fp16`) maps to `coremltools.precision.FLOAT32`/`FLOAT16` via
  `compute_precision` for the TorchScript/Keras paths, and to Ultralytics' own `half` export
  flag for YOLO.
- No accuracy comparison is run: `coremltools`' `MLModel.predict()` only works against the
  real Core ML runtime, which is macOS-only — this project's workers are Linux containers
  (same documented Linux-only constraint `convert_tflite.py` calls out for Ultralytics'
  LiteRT export), so every caster here reports `not_measured` rather than pretending to
  validate against a runtime that isn't present.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from ._convert_common import (
    ConvertContext,
    load_yolo_safely,
    not_measured,
    parse_shape,
    run_convert_op,
)

_NOT_MEASURED_REASON = (
    "Core ML prediction needs the macOS Core ML runtime, not available on this worker"
)


def _compute_precision(precision: str) -> Any:
    import coremltools as ct

    return ct.precision.FLOAT16 if precision == "fp16" else ct.precision.FLOAT32


def _from_torchscript(ctx: ConvertContext) -> dict[str, str]:
    import coremltools as ct
    import torch

    module = torch.jit.load(str(ctx.local_in), map_location="cpu")
    module.eval()
    shape = parse_shape(ctx.params.get("shape"))
    precision = ctx.params.get("precision", "fp16")

    mlmodel = ct.convert(
        module,
        inputs=[ct.TensorType(name="input", shape=shape)],
        convert_to="mlprogram",
        compute_precision=_compute_precision(precision),
    )
    mlmodel.save(str(ctx.local_out / "model.mlpackage"))
    return not_measured(_NOT_MEASURED_REASON)


def _from_keras(ctx: ConvertContext) -> dict[str, str]:
    import coremltools as ct
    import tensorflow as tf

    model = tf.keras.models.load_model(str(ctx.local_in), compile=False, safe_mode=True)
    precision = ctx.params.get("precision", "fp16")

    mlmodel = ct.convert(
        model, convert_to="mlprogram", compute_precision=_compute_precision(precision)
    )
    mlmodel.save(str(ctx.local_out / "model.mlpackage"))
    return not_measured(_NOT_MEASURED_REASON)


def _copy_export(exported_path: Path, local_out: Path) -> None:
    destination = local_out / exported_path.name
    if exported_path.is_dir():
        for member in exported_path.rglob("*"):
            if member.is_file():
                target = destination / member.relative_to(exported_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(member, target)
    else:
        shutil.copyfile(exported_path, destination)


def _from_yolo(ctx: ConvertContext) -> dict[str, str]:
    yolo = load_yolo_safely(ctx.local_in)
    use_fp16 = ctx.params.get("precision", "fp16") == "fp16"
    exported_path = Path(yolo.export(format="coreml", half=use_fp16))
    _copy_export(exported_path, ctx.local_out)
    return not_measured(_NOT_MEASURED_REASON)


_CASTERS = {
    "torchscript": _from_torchscript,
    "keras": _from_keras,
    "yolo": _from_yolo,
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
    **kwargs: Any,
) -> None:
    run_convert_op(
        user_id=user_id, job_id=job_id, model_id=model_id, params=params, operation=operation,
        control=control, event_repo=event_repo, casters=_CASTERS, output_is_directory=True,
        tmp_prefix="mf-convert-coreml-", **kwargs,
    )


__all__ = ["run"]
