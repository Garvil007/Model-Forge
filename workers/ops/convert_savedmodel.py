"""c_savedmodel: convert a model to a TensorFlow SavedModel directory.

A SavedModel is a directory, not a single file, so this op's result is zipped before
upload by `_convert_common.run_convert_op(output_is_directory=True)` — the download name
gets a `.savedmodel.zip` extension, and the UI/API treat it like any other single-object
result; unzipping it back into a directory is a client-side concern, same as it would be
for any other SavedModel export.

- Keras: `tf.keras.Model.export(path)` — the Keras 3 API this image's TensorFlow version
  ships (confirmed against the installed `tensorflow_cpu`/`keras` versions, not assumed);
  the older `model.save(path, save_format="tf")` is Keras 2 and isn't used here. Validated
  by reloading the exported SavedModel with `tf.saved_model.load` and calling its `serve`
  signature against the same input fed to the original Keras model's `.predict`.
- ONNX: `onnx2tf.convert(..., output_folder_path=...)` already writes a `saved_model`
  subdirectory (its default output format alongside the TFLite variants) — this just copies
  that subdirectory's contents up to the op's own output directory rather than the whole
  onnx2tf output tree (which also contains `.tflite` files this op doesn't need).
  Validated the same way as Keras, comparing against `onnxruntime` on the same input.
"""

from __future__ import annotations

import shutil
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from core.similarity import compare_runs

from ._convert_common import ConvertContext, UnsupportedFormatError, not_measured, run_convert_op


def _keras_input_shape(model: Any) -> tuple[int, ...] | None:
    shape = getattr(model, "input_shape", None)
    if shape is None:
        return None
    return tuple(1 if d is None else d for d in shape)


def _from_keras(ctx: ConvertContext) -> dict[str, str]:
    import tensorflow as tf

    model = tf.keras.models.load_model(str(ctx.local_in), compile=False, safe_mode=True)
    model.export(str(ctx.local_out))

    input_shape = _keras_input_shape(model)
    if input_shape is None:
        return not_measured("input shape unknown")

    rng = np.random.default_rng(0)
    sample = rng.standard_normal(input_shape).astype(np.float32)
    reloaded = tf.saved_model.load(str(ctx.local_out))
    serve_fn = reloaded.signatures["serve"]

    def _run_savedmodel(_feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        outputs = serve_fn(tf.constant(sample))
        first = next(iter(outputs.values()))
        return [first.numpy()]

    return compare_runs(
        lambda _f: [model.predict(sample, verbose=0)], _run_savedmodel, {"input": sample}
    )


def _from_onnx(ctx: ConvertContext) -> dict[str, str]:
    import onnx2tf

    out_dir = ctx.tmpdir / "onnx2tf_out"
    out_dir.mkdir(exist_ok=True)
    # onnx2tf's default `tflite_backend="flatbuffer_direct"` never writes a SavedModel at
    # all (confirmed empirically — it only emits `.tflite` files); `tflite_backend=
    # "tf_converter"` is the one that does, writing it straight into `output_folder_path`
    # itself (not a `saved_model/` subdirectory) alongside its own `.tflite` byproducts, so
    # only the actual SavedModel members are copied out below. This backend also needs the
    # optional `tf_keras` package installed (added to `workers/pyproject.toml` and both
    # image lockfiles), confirmed by installing it and re-running this conversion.
    onnx2tf.convert(
        input_onnx_file_path=str(ctx.local_in), output_folder_path=str(out_dir),
        non_verbose=True, tflite_backend="tf_converter",
    )
    saved_model_members = ("assets", "variables", "saved_model.pb", "fingerprint.pb")
    found_any = False
    for name in saved_model_members:
        source = out_dir / name
        if not source.exists():
            continue
        found_any = True
        destination = ctx.local_out / name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, destination)
    if not found_any:
        raise UnsupportedFormatError("onnx2tf produced no SavedModel output")

    import onnxruntime
    import tensorflow as tf

    session = onnxruntime.InferenceSession(str(ctx.local_in))
    model_input = session.get_inputs()[0]
    shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in model_input.shape] or [1]
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(shape).astype(np.float32)

    reloaded = tf.saved_model.load(str(ctx.local_out))
    serve_fn = next(iter(reloaded.signatures.values()))

    def _run_savedmodel(_feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        outputs = serve_fn(tf.constant(sample))
        first = next(iter(outputs.values()))
        return [first.numpy()]

    return compare_runs(
        lambda f: session.run(None, {model_input.name: f["input"]}),
        _run_savedmodel, {"input": sample},
    )


_CASTERS = {
    "keras": _from_keras,
    "onnx": _from_onnx,
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
        tmp_prefix="mf-convert-savedmodel-", **kwargs,
    )


__all__ = ["run"]
