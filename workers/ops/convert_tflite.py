"""c_tflite: convert a model to TensorFlow Lite.

- Keras: `tf.lite.TFLiteConverter.from_keras_model`, `optimizations=[Optimize.DEFAULT]` and
  `target_spec.supported_types=[tf.float16]` when `precision="fp16"`. Validated against the
  loaded Keras model's own `.predict` via `core.model_runner.TfliteModelRunner`.
- ONNX: `onnx2tf.convert()` — the de-facto ONNX->TFLite converter; it writes both an
  `f"{stem}_float32.tflite"` and `f"{stem}_float16.tflite"` into its output folder by
  default (confirmed by running it against a real model, not assumed from its docs), so
  this picks whichever file matches the job's `precision` param. Validated the same way as
  Keras, comparing against `onnxruntime` on the same input.
- YOLO: Ultralytics' own exporter (`YOLO(path).export(format="tflite", half=...)`) — no
  chain needed, Ultralytics ships a direct TFLite exporter. As of Ultralytics 8.4, this
  internally redirects to its newer "LiteRT" export path, which **only runs on Linux x86 or
  macOS** (confirmed empirically on this Windows dev box — `AssertionError: LiteRT export
  only supported on Linux x86 and macOS`); the real worker images (`workers/images/
  cpu-torch`, `cpu-tf`) are Linux containers, so this is a dev-sandbox-only gap, not a
  product one — the corresponding test is skipped on non-Linux with that reasoning rather
  than faking a pass.

  Security note: `YOLO(path)` parses untrusted bytes via `torch.load`, a known pickle-RCE
  surface. Ultralytics' own default (`ultralytics.utils.patches.torch_load`) uses
  `weights_only=False` unless told otherwise — unrestricted unpickling, same class of issue
  as `torch.jit.load`/`keras.load_model` elsewhere in this package (see `fp_cast.py`). This
  module loads YOLO checkpoints through `_convert_common.load_yolo_safely`, which forces
  Ultralytics' opt-in restricted loader (`weights_only=True` against its own class
  allow-list) instead, and refuses with `UnsupportedFormatError` rather than falling back to
  unrestricted unpickling if a checkpoint needs a type outside that allow-list. Full process
  isolation for an untrusted upload is still an infra/ concern, not something this op module
  can provide on its own.
- `torch` (bare PyTorch state_dict): refused, same as every other convert op — no
  architecture to export anywhere, and this project never unpickles a full `nn.Module` from
  an untrusted upload (`torch.load(..., weights_only=False)`) to recover one.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from core.model_runner import TfliteModelRunner
from core.similarity import compare_runs

from ._convert_common import (
    ConvertContext,
    UnsupportedFormatError,
    load_yolo_safely,
    not_measured,
    run_convert_op,
)


def _keras_input_shape(model: Any) -> tuple[int, ...] | None:
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return None
    return tuple(1 if d is None else d for d in shape)


def _from_keras(ctx: ConvertContext) -> dict[str, str]:
    import tensorflow as tf

    model = tf.keras.models.load_model(str(ctx.local_in), compile=False, safe_mode=True)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    precision = ctx.params.get("precision", "fp32")
    if precision == "fp16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
    ctx.local_out.write_bytes(converter.convert())

    input_shape = _keras_input_shape(model)
    if input_shape is None:
        return not_measured("input shape unknown")
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(input_shape).astype(np.float32)
    runner = TfliteModelRunner(ctx.local_out)
    return compare_runs(
        lambda _f: [model.predict(sample, verbose=0)],
        lambda _f: [runner.predict(sample)],
        {"input": sample},
    )


def _from_onnx(ctx: ConvertContext) -> dict[str, str]:
    import onnx2tf

    out_dir = ctx.tmpdir / "onnx2tf_out"
    out_dir.mkdir(exist_ok=True)
    onnx2tf.convert(
        input_onnx_file_path=str(ctx.local_in),
        output_folder_path=str(out_dir),
        non_verbose=True,
        copy_onnx_input_output_names_to_tflite=True,
    )
    precision = ctx.params.get("precision", "fp32")
    stem = ctx.local_in.stem
    picked = out_dir / f"{stem}_{'float16' if precision == 'fp16' else 'float32'}.tflite"
    if not picked.exists():
        candidates = sorted(out_dir.glob("*.tflite"))
        if not candidates:
            raise UnsupportedFormatError("onnx2tf produced no .tflite output")
        picked = candidates[0]
    shutil.copyfile(picked, ctx.local_out)

    import onnxruntime

    session = onnxruntime.InferenceSession(str(ctx.local_in))
    input_name = session.get_inputs()[0].name
    raw_shape = session.get_inputs()[0].shape
    shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in raw_shape] or [1]
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)
    runner = TfliteModelRunner(ctx.local_out)

    # onnx2tf converts a 4-D NCHW graph to TFLite's native NHWC layout (the catalog's
    # c_tflite description says as much: "Converted to NHWC layout"), so the *input* needs
    # the same transpose before being fed to the interpreter — only the output shape
    # mismatch is handled automatically by `core.similarity`'s `_align_layout`.
    tflite_input_shape = runner.input_shape
    if len(shape) == 4 and list(tflite_input_shape) == [shape[0], shape[2], shape[3], shape[1]]:
        tflite_sample = np.transpose(sample, (0, 2, 3, 1))
    else:
        tflite_sample = sample

    return compare_runs(
        lambda f: session.run(None, {input_name: f["input"]}),
        lambda _f: [runner.predict(tflite_sample)],
        {"input": sample},
    )


def _from_yolo(ctx: ConvertContext) -> dict[str, str]:
    import sys

    if sys.platform != "linux":
        raise UnsupportedFormatError(
            "Ultralytics' TFLite (LiteRT) export only runs on Linux x86 or macOS; this "
            "worker image is Linux, but this check also protects a non-Linux dev run"
        )
    yolo = load_yolo_safely(ctx.local_in)
    precision = ctx.params.get("precision", "fp32")
    exported_path = Path(yolo.export(format="tflite", half=(precision == "fp16")))
    shutil.copyfile(exported_path, ctx.local_out)
    return not_measured("YOLO TFLite export has no raw-head comparison implemented yet")


_CASTERS = {
    "keras": _from_keras,
    "onnx": _from_onnx,
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
        control=control, event_repo=event_repo, casters=_CASTERS, tmp_prefix="mf-convert-tflite-",
        **kwargs,
    )


__all__ = ["run"]
