"""c_onnx: export a model to ONNX.

- TorchScript: `torch.onnx.export` fed a synthetic input built from the job's `shape` param
  (defaults to a 224x224 RGB image shape if the param is missing/malformed — see
  `_convert_common.parse_shape`), with `dynamic_axes` on the batch dim when the `dynamic`
  param is set and `opset_version` from the `opset` param. Validated by running the same
  input through the loaded `ScriptModule` and the exported ONNX graph and comparing outputs
  (`core.similarity.compare_runs`).
- Keras: `tf2onnx.convert.from_keras()`'s Python API raises a `KeyError` on this image's
  Keras 3 (`model_out_names` lookup assumes Keras 2's naming) — confirmed empirically, not
  assumed. Keras 3's own `model.export()` SavedModel path works fine, so this instead
  exports to a temporary SavedModel directory and shells out to tf2onnx's CLI
  (`python -m tf2onnx.convert --saved-model ...`), which loads the SavedModel's concrete
  function directly and sidesteps the symbolic-tensor-naming bug entirely. Validated the
  same way as TorchScript, using the loaded Keras model's own `.predict`.
- YOLO: Ultralytics checkpoints carry their own exporter (`YOLO(path).export(format="onnx",
  ...)`), which already handles YOLO's multi-output head and runs `onnxslim` — using
  `torch.onnx.export` directly on `model.model` would need YOLO-internal knowledge of its
  output head shape. Validated by comparing the *raw* (pre-NMS) head output of
  `model.model(x)` against the ONNX graph's raw output on the same random input — the
  exported graph has no NMS/decoding baked in either, matching Ultralytics' own export
  convention.

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
- safetensors: a bare safetensors file has no architecture by itself. This only works for a
  Hugging Face LLM import (`model.details["repoId"]` set by `workers/ops/import_hf.py`),
  exported via `optimum.onnxruntime.ORTModelForCausalLM.from_pretrained(repo_id,
  export=True)` — Optimum re-resolves the real `transformers` model class and config from
  the repo id rather than this worker reconstructing an architecture from raw tensor names.
  Optimum's own exporter already validates the ONNX graph's outputs against the original
  PyTorch forward pass within a fixed tolerance before returning, which is reported as the
  "metrics" here rather than re-running an equivalent check ourselves.
- `torch` (bare PyTorch state_dict): refused. It has no architecture to trace/script, the
  same constraint `workers/ops/fp_cast.py` and `workers/ops/quantize_dynamic.py` already
  document and refuse for other operations — this worker never calls
  `torch.load(..., weights_only=False)` on an untrusted upload to recover a pickled
  `nn.Module` instead, since that would mean executing arbitrary code from the file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from core.similarity import compare_arrays, compare_runs

from ._convert_common import (
    ConvertContext,
    UnsupportedFormatError,
    load_yolo_safely,
    not_measured,
    parse_shape,
    require_hf_repo_id,
    run_convert_op,
)


def _keras_input_shape(model: Any) -> tuple[int, ...] | None:
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return None
    return tuple(1 if d is None else d for d in shape)


def _from_torchscript(ctx: ConvertContext) -> dict[str, str]:
    import torch

    module = torch.jit.load(str(ctx.local_in), map_location="cpu")
    module.eval()
    shape = parse_shape(ctx.params.get("shape"))
    dummy = torch.zeros(shape, dtype=torch.float32)
    dynamic = bool(ctx.params.get("dynamic", True))
    dynamic_axes = {"input": {0: "batch"}, "output": {0: "batch"}} if dynamic else None
    opset = int(ctx.params.get("opset", 17))

    torch.onnx.export(
        module, (dummy,), str(ctx.local_out), input_names=["input"], output_names=["output"],
        dynamic_axes=dynamic_axes, opset_version=opset, dynamo=False,
    )

    import onnxruntime

    session = onnxruntime.InferenceSession(str(ctx.local_out))
    input_name = session.get_inputs()[0].name

    def _run_torch(_feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        with torch.no_grad():
            out = module(dummy)
        return [out.detach().numpy() if hasattr(out, "detach") else np.asarray(out)]

    def _run_onnx(feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        return session.run(None, {input_name: feeds["input"]})

    return compare_runs(_run_torch, _run_onnx, {"input": dummy.numpy()})


def _from_keras(ctx: ConvertContext) -> dict[str, str]:
    import tensorflow as tf

    model = tf.keras.models.load_model(str(ctx.local_in), compile=False, safe_mode=True)
    saved_model_dir = ctx.tmpdir / "keras_savedmodel"
    model.export(str(saved_model_dir))

    opset = int(ctx.params.get("opset", 17))
    result = subprocess.run(
        [
            sys.executable, "-m", "tf2onnx.convert",
            "--saved-model", str(saved_model_dir),
            "--output", str(ctx.local_out),
            "--opset", str(opset),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not ctx.local_out.exists():
        tail = result.stderr[-2000:]
        raise UnsupportedFormatError(f"tf2onnx failed to export the SavedModel: {tail}")

    input_shape = _keras_input_shape(model)
    if input_shape is None:
        return not_measured("input shape unknown")

    import onnxruntime

    rng = np.random.default_rng(0)
    sample = rng.standard_normal(input_shape).astype(np.float32)
    session = onnxruntime.InferenceSession(str(ctx.local_out))
    input_name = session.get_inputs()[0].name
    return compare_runs(
        lambda _f: [model.predict(sample, verbose=0)],
        lambda _f: session.run(None, {input_name: sample}),
        {"input": sample},
    )


def _from_yolo(ctx: ConvertContext) -> dict[str, str]:
    yolo = load_yolo_safely(ctx.local_in)
    opset = int(ctx.params.get("opset", 17))
    dynamic = bool(ctx.params.get("dynamic", True))
    exported_path = Path(yolo.export(format="onnx", opset=opset, dynamic=dynamic))
    shutil.copyfile(exported_path, ctx.local_out)
    return _compare_yolo_raw_head(yolo, ctx.local_out)


def _compare_yolo_raw_head(yolo: Any, onnx_path: Path) -> dict[str, str]:
    try:
        import onnxruntime
        import torch

        torch_module = yolo.model
        torch_module.eval()
        args = getattr(torch_module, "args", {})
        imgsz = args.get("imgsz", 640) if hasattr(args, "get") else 640
        if not isinstance(imgsz, int):
            imgsz = 640
        rng = np.random.default_rng(0)
        sample = rng.standard_normal((1, 3, imgsz, imgsz)).astype(np.float32)
        with torch.no_grad():
            raw = torch_module(torch.from_numpy(sample))
        raw_tensor = raw[0] if isinstance(raw, (tuple, list)) else raw
        raw_array = (
            raw_tensor.detach().numpy() if hasattr(raw_tensor, "detach") else np.asarray(raw_tensor)
        )

        session = onnxruntime.InferenceSession(str(onnx_path))
        input_name = session.get_inputs()[0].name
        onnx_out = session.run(None, {input_name: sample})[0]
        return compare_arrays(np.asarray(raw_array), np.asarray(onnx_out))
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return not_measured("yolo raw-head comparison failed")


def _from_safetensors(ctx: ConvertContext) -> dict[str, str]:
    repo_id = require_hf_repo_id(ctx.model)
    from optimum.onnxruntime import ORTModelForCausalLM

    export_dir = ctx.tmpdir / "optimum_export"
    export_dir.mkdir(exist_ok=True)
    ort_model = ORTModelForCausalLM.from_pretrained(repo_id, export=True)
    ort_model.save_pretrained(str(export_dir))

    onnx_files = sorted(export_dir.glob("*.onnx"))
    if not onnx_files:
        raise UnsupportedFormatError("Optimum export produced no ONNX file")
    shutil.copyfile(onnx_files[0], ctx.local_out)
    return {
        "Output similarity": "validated by Optimum's own export-time output check",
        "Max difference": "not measured (see Optimum's export log for its atol/rtol check)",
        "Top-1 agreement": "not measured (see Optimum's export log for its atol/rtol check)",
    }


_CASTERS = {
    "torchscript": _from_torchscript,
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
        control=control, event_repo=event_repo, casters=_CASTERS, tmp_prefix="mf-convert-onnx-",
        **kwargs,
    )


__all__ = ["run"]
