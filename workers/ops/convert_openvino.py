"""c_openvino: convert a model to OpenVINO IR (a directory of a `.xml` graph + `.bin`
weights, zipped before upload like `convert_savedmodel.py`'s SavedModel output).

- ONNX / Keras: `openvino.convert_model()` accepts an ONNX file path or a loaded Keras
  model object directly (confirmed empirically against this image's installed `openvino`
  version) — no chain through ONNX needed for either.
- YOLO: Ultralytics' own exporter (`YOLO(path).export(format="openvino", ...)`), which
  writes a `<stem>_openvino_model/` directory containing `metadata.yaml` plus the `.xml`/
  `.bin` pair (confirmed by running it) — copied into this op's own output directory.

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
- safetensors (HF LLM only): the one genuine **chain** in this Convert-tab implementation
  (see `core/convert_chain.py`), because there's no library that goes straight from raw
  safetensors weights to OpenVINO IR. Hop 1 reuses `convert_onnx.py`'s safetensors caster
  (Optimum export to ONNX, needs `model.details["repoId"]`); hop 2 is
  `openvino.convert_model()` on that ONNX file. Each hop emits its own `JobEvent` under the
  op's one "Converting to OpenVINO IR" stage, per `job_stages.py`'s fixed 3-stage contract
  for every convert op.
- `torch` (bare PyTorch state_dict): refused — no architecture, same as every other convert
  op (see `workers/ops/fp_cast.py`'s docstring for why this project never unpickles a full
  `nn.Module` from an untrusted upload to work around that).
- Precision param: `fp32`/`fp16` set `openvino.save_model`'s `compress_to_fp16` flag
  (confirmed via its docstring: FP16 weight compression is applied at save time, not
  during `convert_model`). `int8` runs `nncf.compress_weights()` (default
  `CompressWeightsMode.INT8_ASYM`) on the converted model before saving — this is
  calibration-free *weight-only* compression, not full static activation quantization (the
  catalog's `c_openvino` has no calibration-data param, unlike `q_int8_static`), confirmed
  working against a real converted model in this environment.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from core.convert_chain import ChainHop, run_chain
from core.similarity import compare_arrays

from ._convert_common import ConvertContext, load_yolo_safely, not_measured, run_convert_op
from .convert_onnx import _from_safetensors as _safetensors_to_onnx


def _save_openvino(ov_model: Any, out_dir: Path, precision: str) -> None:
    import nncf
    import openvino as ov

    out_dir.mkdir(parents=True, exist_ok=True)
    if precision == "int8":
        ov_model = nncf.compress_weights(ov_model)
        ov.save_model(ov_model, str(out_dir / "model.xml"), compress_to_fp16=False)
    else:
        ov.save_model(ov_model, str(out_dir / "model.xml"), compress_to_fp16=(precision == "fp16"))


def _compare_openvino(ov_model: Any, out_dir: Path, sample: np.ndarray) -> dict[str, str]:
    try:
        import openvino as ov

        original_compiled = ov.compile_model(ov_model)
        original_out = original_compiled(sample)
        first_original = next(iter(original_out.values()))

        result_compiled = ov.compile_model(str(out_dir / "model.xml"))
        result_out = result_compiled(sample)
        first_result = next(iter(result_out.values()))
        return compare_arrays(np.asarray(first_original), np.asarray(first_result))
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return not_measured("openvino comparison failed")


def _from_onnx(ctx: ConvertContext) -> dict[str, str]:
    import onnxruntime
    import openvino as ov

    ov_model = ov.convert_model(str(ctx.local_in))
    precision = ctx.params.get("precision", "fp16")
    _save_openvino(ov_model, ctx.local_out, precision)

    session = onnxruntime.InferenceSession(str(ctx.local_in))
    model_input = session.get_inputs()[0]
    shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in model_input.shape] or [1]
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)
    return _compare_openvino(ov_model, ctx.local_out, sample)


def _from_keras(ctx: ConvertContext) -> dict[str, str]:
    import openvino as ov
    import tensorflow as tf

    model = tf.keras.models.load_model(str(ctx.local_in), compile=False, safe_mode=True)
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return not_measured("input shape unknown")
    shape = tuple(1 if d is None else d for d in shape)

    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)

    # `openvino.convert_model` needs a concrete `example_input` to trace a Keras model
    # object directly (confirmed empirically: without it, it raises "Cannot take the
    # length of shape with unknown rank" and asks for exactly this).
    ov_model = ov.convert_model(model, example_input=sample)
    precision = ctx.params.get("precision", "fp16")
    _save_openvino(ov_model, ctx.local_out, precision)
    return _compare_openvino(ov_model, ctx.local_out, sample)


def _from_safetensors(ctx: ConvertContext) -> dict[str, str]:
    import openvino as ov

    def _hop_to_onnx(_path_in: Path, path_out: Path) -> None:
        sub_ctx = ConvertContext(
            model=ctx.model, local_in=ctx.local_in, local_out=path_out, tmpdir=ctx.tmpdir,
            params=ctx.params, control=ctx.control, event_repo=ctx.event_repo,
            user_id=ctx.user_id, job_id=ctx.job_id, stage=ctx.stage,
        )
        _safetensors_to_onnx(sub_ctx)

    def _hop_to_openvino(path_in: Path, path_out: Path) -> None:
        ov_model = ov.convert_model(str(path_in))
        precision = ctx.params.get("precision", "fp16")
        _save_openvino(ov_model, path_out, precision)

    run_chain(
        (
            ChainHop("Exporting to ONNX via Optimum", _hop_to_onnx, ".onnx"),
            ChainHop("Converting ONNX to OpenVINO IR", _hop_to_openvino, ""),
        ),
        ctx.local_in, ctx.local_out, tmpdir=ctx.tmpdir, event_repo=ctx.event_repo,
        user_id=ctx.user_id, job_id=ctx.job_id, stage=ctx.stage,
    )
    return {
        "Output similarity": "not measured (HF LLM chain: validated by Optimum's export check)",
        "Max difference": "not measured",
        "Top-1 agreement": "not measured",
    }


def _from_yolo(ctx: ConvertContext) -> dict[str, str]:
    yolo_openvino_export(ctx)
    return not_measured("YOLO OpenVINO export has no raw-head comparison implemented yet")


def yolo_openvino_export(ctx: ConvertContext) -> None:
    yolo = load_yolo_safely(ctx.local_in)
    use_fp16 = ctx.params.get("precision") == "fp16"
    exported_dir = Path(yolo.export(format="openvino", half=use_fp16))
    ctx.local_out.mkdir(parents=True, exist_ok=True)
    for member in exported_dir.rglob("*"):
        if member.is_file():
            destination = ctx.local_out / member.relative_to(exported_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(member, destination)


_CASTERS = {
    "onnx": _from_onnx,
    "keras": _from_keras,
    "yolo": _from_yolo,
    "safetensors": _from_safetensors,
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
        tmp_prefix="mf-convert-openvino-", **kwargs,
    )


__all__ = ["run"]
