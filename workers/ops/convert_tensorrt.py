"""c_tensorrt: build a TensorRT engine from ONNX (direct) or a YOLO checkpoint (exported to
ONNX first via `convert_onnx.py`'s own YOLO caster, reused rather than duplicated — same
precedent as `convert_openvino.py` reusing `convert_onnx._from_safetensors`).

- fp32 / fp16: `tensorrt.Builder` parses the ONNX graph, builds a serialized engine with
  `BuilderFlag.FP16` set for the fp16 case, and the result is validated by running the
  engine (via `tensorrt.Runtime` + `cuda-python`'s `cudart` for device buffers) against
  `onnxruntime` on the same random input, same "best-effort, not a correctness gate" pattern
  as `core.similarity.compare_runs`. Building (and running) an engine needs a real CUDA
  device, so this op only works on a real GPU worker — there is no CPU fallback, matching
  this project's existing GPU-only ops (`q_gptq`/`q_awq`/`q_nf4`).
- int8: refused with a clear `UnsupportedFormatError`. The catalog's `calib` param is a
  `type="file"` upload, and `type="file"` params still have no S3 upload plumbing wired to
  worker storage anywhere in this project (see `workers/ops/_llm_common.py`'s
  `resolve_calibration_dataset` and `docs/PROGRESS.md`'s Day 14/17/18 entries for the same
  documented gap) — faking calibration with synthetic random data would silently produce a
  misleadingly-labeled "near-lossless" engine, which is worse than refusing outright.
- Jetson Orin is never built here: TensorRT engines only run on the exact GPU model and
  TensorRT version they were built for, and this service has no Jetson build hardware. For
  that target the op instead hands back the plain ONNX file plus a ready `trtexec` command
  (and refuses int8 the same way, since there's no calibration data to embed in the command
  either) so the user can build the engine themselves on-device.
- A bare `torch` (state_dict) or `torchscript` source is refused: TensorRT's ONNX parser is
  the only path in here, and neither format is in `c_tensorrt`'s `source_formats` (ONNX,
  YOLO only) — same convention as every other `convert_*.py` module, whose `_CASTERS` dict
  simply omits keys it has no caster for.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from core.similarity import compare_arrays

from ._convert_common import ConvertContext, UnsupportedFormatError, not_measured, run_convert_op
from .convert_onnx import _from_yolo as _yolo_to_onnx

_GPU_LABELS = {"t4": "T4", "l4": "L4", "a100": "A100", "h100": "H100", "jetson": "Jetson Orin"}


def _trtexec_command(precision: str) -> str:
    flags = {
        "fp32": "",
        "fp16": " --fp16",
        "int8": " --int8 --calib=<your_calibration_cache>",
    }[precision]
    return f"trtexec --onnx=model.onnx --saveEngine=model.engine{flags}"


def _build_jetson_bundle(ctx: ConvertContext, onnx_path: Path, precision: str) -> dict[str, str]:
    (ctx.local_out / "model.onnx").write_bytes(onnx_path.read_bytes())
    (ctx.local_out / "trtexec_command.txt").write_text(_trtexec_command(precision) + "\n")
    (ctx.local_out / "README.txt").write_text(
        "Jetson Orin isn't built by this service — TensorRT engines only run on the exact "
        "GPU model and TensorRT version they were built with, and we don't have Jetson "
        "build hardware. Run the command in trtexec_command.txt on the Jetson device "
        "itself (with trtexec from the TensorRT version installed there) to build the "
        f"engine.\n\nChosen precision: {precision.upper()}\n"
        + (
            "\nINT8 also needs a calibration cache built from representative inputs on "
            "the device — <your_calibration_cache> in the command is a placeholder; see "
            "TensorRT's trtexec documentation for how to build one.\n"
            if precision == "int8"
            else ""
        )
    )
    metrics = not_measured("Jetson engine isn't built here — see trtexec_command.txt")
    metrics["GPU target"] = _GPU_LABELS["jetson"]
    return metrics


def _detect_gpu_name() -> str:
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        first_line = output.stdout.strip().splitlines()
        return first_line[0].strip() if first_line else "unknown"
    except Exception:  # noqa: BLE001 — a missing/unreadable nvidia-smi must not fail the job
        return "unknown"


def _build_engine(onnx_bytes: bytes, *, fp16: bool) -> bytes:
    import tensorrt as trt

    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    if not parser.parse(onnx_bytes):
        errors = "; ".join(str(parser.get_error(i)) for i in range(parser.num_errors))
        raise UnsupportedFormatError(f"TensorRT could not parse the ONNX graph: {errors}")

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 4 << 30)
    if fp16:
        config.set_flag(trt.BuilderFlag.FP16)

    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        raise UnsupportedFormatError("TensorRT engine build failed — see worker logs")
    return bytes(serialized)


def _run_engine(engine_bytes: bytes, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Runs a built engine on `feeds` via TensorRT's execution-v3 tensor API, using
    `cuda-python`'s `cudart` directly for device allocation/copy rather than pulling in
    pycuda — `cuda-python` is the lighter, NVIDIA-maintained binding and this only needs
    raw malloc/memcpy, nothing pycuda's higher-level context management adds."""
    import tensorrt as trt
    from cuda import cudart

    def check(result: tuple[Any, ...]) -> Any:
        err, *rest = result
        if err != cudart.cudaError_t.cudaSuccess:
            raise RuntimeError(f"CUDA error: {err}")
        return rest[0] if len(rest) == 1 else tuple(rest)

    logger = trt.Logger(trt.Logger.WARNING)
    runtime = trt.Runtime(logger)
    engine = runtime.deserialize_cuda_engine(engine_bytes)
    context = engine.create_execution_context()

    device_ptrs: dict[str, int] = {}
    host_outputs: dict[str, np.ndarray] = {}
    try:
        for i in range(engine.num_io_tensors):
            name = engine.get_tensor_name(i)
            is_input = engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT
            if is_input:
                array = np.ascontiguousarray(feeds[name], dtype=np.float32)
                context.set_input_shape(name, array.shape)
            else:
                shape = tuple(context.get_tensor_shape(name))
                array = np.empty(shape, dtype=np.float32)

            device_ptr = check(cudart.cudaMalloc(array.nbytes))
            device_ptrs[name] = device_ptr
            context.set_tensor_address(name, device_ptr)

            if is_input:
                check(
                    cudart.cudaMemcpy(
                        device_ptr, array.ctypes.data, array.nbytes,
                        cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,
                    )
                )
            else:
                host_outputs[name] = array

        stream = check(cudart.cudaStreamCreate())
        try:
            if not context.execute_async_v3(stream):
                raise RuntimeError("TensorRT execution did not complete")
            check(cudart.cudaStreamSynchronize(stream))
        finally:
            cudart.cudaStreamDestroy(stream)

        for name, array in host_outputs.items():
            check(
                cudart.cudaMemcpy(
                    array.ctypes.data, device_ptrs[name], array.nbytes,
                    cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
                )
            )
        return host_outputs
    finally:
        for device_ptr in device_ptrs.values():
            cudart.cudaFree(device_ptr)


def _validate_engine(engine_bytes: bytes, onnx_path: Path) -> dict[str, str]:
    try:
        import onnxruntime

        session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        model_input = session.get_inputs()[0]
        shape = [d if isinstance(d, int) and d > 0 else 1 for d in model_input.shape] or [1]
        rng = np.random.default_rng(0)
        sample = rng.standard_normal(shape).astype(np.float32)
        onnx_out = session.run(None, {model_input.name: sample})[0]

        trt_outputs = _run_engine(engine_bytes, {model_input.name: sample})
        trt_out = next(iter(trt_outputs.values()))
        return compare_arrays(np.asarray(onnx_out), np.asarray(trt_out))
    except Exception:  # noqa: BLE001 — a measurement failure must not fail the job
        return not_measured("TensorRT engine execution check failed, or no GPU in this environment")


def _engine_readme(gpu: str, gpu_name: str, trt_version: str, precision: str) -> str:
    return (
        "This TensorRT engine is bound to the exact GPU model and TensorRT version it was "
        "built with. It will NOT load on a different GPU model or a different TensorRT "
        f"version — rebuild it on the target hardware if either changes.\n\n"
        f"Chosen target: {_GPU_LABELS.get(gpu, gpu)}\n"
        f"Actually built on: {gpu_name}\n"
        f"TensorRT version: {trt_version}\n"
        f"Precision: {precision.upper()}\n"
    )


def _build_engine_bundle(
    ctx: ConvertContext, onnx_path: Path, *, gpu: str, fp16: bool
) -> dict[str, str]:
    import tensorrt as trt

    onnx_bytes = onnx_path.read_bytes()
    engine_bytes = _build_engine(onnx_bytes, fp16=fp16)
    (ctx.local_out / "model.engine").write_bytes(engine_bytes)

    gpu_name = _detect_gpu_name()
    precision = "fp16" if fp16 else "fp32"
    (ctx.local_out / "README.txt").write_text(
        _engine_readme(gpu, gpu_name, trt.__version__, precision)
    )

    metrics = _validate_engine(engine_bytes, onnx_path)
    metrics["GPU target"] = _GPU_LABELS.get(gpu, gpu)
    metrics["Built on"] = gpu_name
    metrics["TensorRT version"] = trt.__version__
    return metrics


def _dispatch(ctx: ConvertContext, onnx_path: Path) -> dict[str, str]:
    gpu = ctx.params.get("gpu", "l4")
    precision = ctx.params.get("precision", "fp16")

    if gpu == "jetson":
        return _build_jetson_bundle(ctx, onnx_path, precision)
    if precision == "int8":
        raise UnsupportedFormatError(
            "INT8 needs calibration inputs, and uploading a calibration file isn't wired "
            "to worker storage yet (the same project-wide gap as every other "
            "type=\"file\" param — see docs/PROGRESS.md); choose FP32 or FP16 for now"
        )
    return _build_engine_bundle(ctx, onnx_path, gpu=gpu, fp16=(precision == "fp16"))


def _from_onnx(ctx: ConvertContext) -> dict[str, str]:
    return _dispatch(ctx, ctx.local_in)


def _from_yolo(ctx: ConvertContext) -> dict[str, str]:
    onnx_path = ctx.tmpdir / "yolo_export.onnx"
    yolo_ctx = ConvertContext(
        model=ctx.model, local_in=ctx.local_in, local_out=onnx_path, tmpdir=ctx.tmpdir,
        params=ctx.params, control=ctx.control, event_repo=ctx.event_repo,
        user_id=ctx.user_id, job_id=ctx.job_id, stage=ctx.stage,
    )
    _yolo_to_onnx(yolo_ctx)
    return _dispatch(ctx, onnx_path)


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
        control=control, event_repo=event_repo, casters=_CASTERS, output_is_directory=True,
        tmp_prefix="mf-convert-tensorrt-", **kwargs,
    )


__all__ = ["run"]
