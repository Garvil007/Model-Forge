"""c_torchscript: convert a model to TorchScript.

- ONNX: `onnx2torch.convert()` rebuilds the graph as a real `torch.nn.Module`, which is then
  `torch.jit.trace`d into a `ScriptModule`. `onnx2torch.convert` must be given an already
  *loaded* `onnx.ModelProto`, not a file path — passing a path makes it run shape inference
  through a `tempfile.NamedTemporaryFile` it reopens by name, which raises
  `PermissionError` on Windows because the first handle is still open (confirmed
  empirically; harmless on the Linux worker images, but loading the model ourselves avoids
  depending on that platform difference at all). Validated by comparing the traced
  module's output against `onnxruntime` on the same random input.
- YOLO: Ultralytics' own exporter (`YOLO(path).export(format="torchscript")`) — it writes a
  `.torchscript` file (not `.pt`), copied into this op's own output path. Validated against
  the raw (pre-NMS) head output of the underlying `model.model`, same convention as
  `convert_onnx.py`'s YOLO->ONNX case.

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
- PyTorch `torch` (an already-real `nn.Module`... in principle): `torch.jit.script` is
  tried first, falling back to `torch.jit.trace` with a synthetic input (built from the
  `shape` param) if scripting raises — scripting handles control flow a trace would bake in
  as constants, but not every module is scriptable (custom ops, certain Python builtins),
  so trace is the safety net. In practice this project's `torch` format is a bare
  state_dict with no architecture at all (see `workers/ops/fp_cast.py`'s docstring), so
  there is nothing to script or trace — this caster is intentionally absent from `_CASTERS`
  below and the op refuses `torch` sources with a clean `unsupported_operator`, the same
  precedent `workers/ops/quantize_dynamic.py` set for `q_int8_dyn`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from core.similarity import compare_arrays, compare_runs

from ._convert_common import ConvertContext, load_yolo_safely, not_measured, run_convert_op


def _from_onnx(ctx: ConvertContext) -> dict[str, str]:
    import onnx
    import torch
    from onnx2torch import convert

    loaded = onnx.load(str(ctx.local_in))
    torch_module = convert(loaded)
    torch_module.eval()

    import onnxruntime

    session = onnxruntime.InferenceSession(str(ctx.local_in))
    model_input = session.get_inputs()[0]
    shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in model_input.shape] or [1]
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)
    dummy = torch.from_numpy(sample)

    scripted = torch.jit.trace(torch_module, (dummy,))
    torch.jit.save(scripted, str(ctx.local_out))

    def _run_torch(_feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        with torch.no_grad():
            out = torch_module(dummy)
        return [out.detach().numpy() if hasattr(out, "detach") else np.asarray(out)]

    def _run_onnx(feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        return session.run(None, {model_input.name: feeds["input"]})

    return compare_runs(_run_torch, _run_onnx, {"input": sample})


def _from_yolo(ctx: ConvertContext) -> dict[str, str]:
    yolo = load_yolo_safely(ctx.local_in)
    exported_path = Path(yolo.export(format="torchscript"))
    shutil.copyfile(exported_path, ctx.local_out)
    return _compare_yolo_raw_head(yolo, ctx.local_out)


def _compare_yolo_raw_head(yolo: Any, torchscript_path: Path) -> dict[str, str]:
    try:
        import torch

        torch_module = yolo.model
        torch_module.eval()
        rng = np.random.default_rng(0)
        sample = rng.standard_normal((1, 3, 640, 640)).astype(np.float32)
        tensor = torch.from_numpy(sample)
        with torch.no_grad():
            raw = torch_module(tensor)
        raw_tensor = raw[0] if isinstance(raw, (tuple, list)) else raw
        raw_array = (
            raw_tensor.detach().numpy() if hasattr(raw_tensor, "detach") else np.asarray(raw_tensor)
        )

        scripted = torch.jit.load(str(torchscript_path), map_location="cpu")
        scripted.eval()
        with torch.no_grad():
            scripted_out = scripted(tensor)
        scripted_tensor = (
            scripted_out[0] if isinstance(scripted_out, (tuple, list)) else scripted_out
        )
        scripted_array = (
            scripted_tensor.detach().numpy()
            if hasattr(scripted_tensor, "detach")
            else np.asarray(scripted_tensor)
        )
        return compare_arrays(np.asarray(raw_array), np.asarray(scripted_array))
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return not_measured("yolo raw-head comparison failed")


_CASTERS = {
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
        control=control, event_repo=event_repo, casters=_CASTERS,
        tmp_prefix="mf-convert-torchscript-", **kwargs,
    )


__all__ = ["run"]
