"""Shared plumbing for the Distillation-tab vision/other ops (`distill_response.py` /
`d_logit`, `distill_feature.py` / `d_feature`): loading a runnable teacher, building a
small PyTorch student from one of the catalog's size presets, a knowledge-distillation
loss, and the download -> build student -> train -> measure -> upload -> job-status
runner both ops share. (`distill_llm.py` / `d_llm` is Transformers-specific enough to
have its own module.)

Teacher loading, by source format:

- `onnx`/`tflite`/`torchscript`: `core.model_runner.create_runner` — already unifies
  these three behind one `predict(batch) -> array`.
- `keras`: loaded directly here (`tf.keras.models.load_model`), same as every other
  op's Keras path.
- `yolo`: `_convert_common.load_yolo_safely`, forward-passed through the loaded
  `ultralytics.YOLO.model` (a real `nn.Module`). YOLO's detection head returns
  per-anchor boxes, not classification logits — reshaped to one flat vector per sample
  and treated as a generic "response" to match, a documented simplification, not real
  class semantics.
- a bare `torch` (state_dict) source has no architecture to run forward passes
  through, the same constraint every other op in this package documents for that
  format — refused with `UnsupportedFormatError`.

The student is NOT a literal half-width/half-depth clone of the teacher's own
architecture — building that generically for an arbitrary ONNX graph, TFLite graph, or
YOLO detection head would need real per-format architecture introspection this module
doesn't implement (the same class of simplification `prune_structured.py`'s Keras path
documents for TF-MOT). Instead each preset picks a base channel count / stage count for
a small, generic conv-or-MLP network (conv for image-shaped input, MLP otherwise) sized
so the preset ordering (`compact` < `half_width` < `half_depth`) still holds in practice.
`student="custom"` (an uploaded architecture) isn't wired to worker storage yet, the same
gap `workers/ops/prune_structured.py`'s `_finetune_yolo` documents for `train_data` —
refused the same way.

Feature-based distillation (`use_feature_matching=True`) adds one more term to the loss:
an MSE between the student's and teacher's intermediate feature, found generically on
both sides as "the input to the last `Linear` (or, failing that, last `Conv2d`)
submodule" (`find_feature_hook_module`) rather than any real per-architecture notion of
"stage" or "block" — a `layers="stages"`/`"auto"` request degrades to this same single
hook point, documented here rather than in each op. A learned `nn.Linear` adapter
projects the student's feature width onto the teacher's. Only YOLO teachers (a genuine
eager `nn.Module` graph) can be hooked this way — Python forward hooks don't fire on a
*traced*/*scripted* TorchScript submodule called from inside the TorchScript
interpreter (verified empirically; see `_TorchScriptTeacherAdapter`'s docstring), and
Keras has no torch module to hook at all — both fall back to response-only
distillation with a noted reason.

Training runs on synthetic inputs sampled from the teacher's own response surface
(random tensors shaped like its input, teacher's output as the soft target) rather than
the user's uploaded `train_data`: `type="file"` params have no S3 upload plumbing wired
to worker storage yet (`workers/ops/_llm_common.py::resolve_calibration_text` documents
the same gap for `imatrix_text`). This keeps the "Training student" stage genuinely
running real gradient steps against a real loss today, and degrades the result's
metrics with an honest note rather than failing the (required) param outright.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core import model_runner
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError
from core.similarity import compare_arrays

from ._convert_common import UnsupportedFormatError, load_yolo_safely, s3_client
from ._prune_common import input_suffix

_DEFAULT_IMAGE_SHAPE = (1, 3, 224, 224)
_YOLO_INPUT_SHAPE = (1, 3, 640, 640)
_BATCH_SIZE = 8
_BATCHES_PER_EPOCH = 4
_FEATURE_LOSS_WEIGHT = 0.3

STUDENT_PRESETS: dict[str, dict[str, int]] = {
    "half_width": {"base_channels": 32, "stages": 4},
    "half_depth": {"base_channels": 48, "stages": 2},
    "compact": {"base_channels": 16, "stages": 2},
}


# --------------------------------------------------------------------------- teacher


class _KerasTeacherRunner:
    def __init__(self, path: Path) -> None:
        import tensorflow as tf

        self._model = tf.keras.models.load_model(str(path), compile=False, safe_mode=True)

    @property
    def input_shape(self) -> tuple[int, ...]:
        return tuple(1 if dim is None else dim for dim in self._model.input_shape)

    def predict(self, batch: np.ndarray) -> np.ndarray:
        return np.asarray(self._model.predict(batch, verbose=0))

    def torch_module(self) -> Any | None:
        return None  # no torch submodule graph to hook for feature matching


class _YoloTeacherRunner:
    def __init__(self, path: Path) -> None:
        yolo = load_yolo_safely(path)
        self._net = yolo.model
        self._net.eval()

    @property
    def input_shape(self) -> tuple[int, ...]:
        return _YOLO_INPUT_SHAPE

    def predict(self, batch: np.ndarray) -> np.ndarray:
        import torch

        with torch.no_grad():
            output = self._net(torch.from_numpy(np.asarray(batch, dtype=np.float32)))
        if isinstance(output, (list, tuple)):
            output = output[0]
        array = output.numpy() if hasattr(output, "numpy") else np.asarray(output)
        return array.reshape(array.shape[0], -1) if array.ndim > 2 else array

    def torch_module(self) -> Any | None:
        return self._net


class _TorchScriptTeacherAdapter:
    """Wraps `core.model_runner.TorchScriptModelRunner`, without changing that runner's
    own public contract (used elsewhere unmodified, e.g. convert ops).

    `torch_module()` returns `None` rather than the underlying `ScriptModule`: Python
    forward hooks registered on a *traced*/*scripted* submodule don't fire when that
    submodule is called from within the TorchScript interpreter (verified empirically —
    only a hook on the top-level scripted module itself would see traffic, which is no
    more useful than the response-only KD loss already computes from `predict()`). YOLO
    is the only format here backed by a genuine eager `nn.Module` graph, so it's the
    only one `run_distillation_op` can hook for a real intermediate feature; TorchScript
    and Keras both cleanly fall back to response-only distillation with a noted reason.
    """

    def __init__(self, runner: Any) -> None:
        self._runner = runner

    @property
    def input_shape(self) -> tuple[int, ...]:
        return _DEFAULT_IMAGE_SHAPE  # TorchScript carries no declared input shape

    def predict(self, batch: np.ndarray) -> np.ndarray:
        return self._runner.predict(batch)

    def torch_module(self) -> Any | None:
        return None


def load_teacher_runner(model_format: str, local_in: Path) -> Any:
    """Returns a `predict(batch) -> array` adapter plus an `input_shape` property plus
    a `torch_module() -> nn.Module | None` hook (used by feature-based distillation to
    find an intermediate layer to match) — one small protocol every branch below meets."""
    if model_format == "torchscript":
        return _TorchScriptTeacherAdapter(model_runner.create_runner(model_format, local_in))
    if model_format in ("onnx", "tflite"):
        runner = model_runner.create_runner(model_format, local_in)
        runner.torch_module = lambda: None  # type: ignore[attr-defined]
        return runner
    if model_format == "keras":
        return _KerasTeacherRunner(local_in)
    if model_format == "yolo":
        return _YoloTeacherRunner(local_in)
    raise UnsupportedFormatError(
        f"distillation needs a runnable teacher to generate soft targets; a bare "
        f"{model_format!r} file carries no architecture to run forward passes through"
    )


# --------------------------------------------------------------------------- student


try:
    import torch as _torch
except ImportError:  # pragma: no cover — this module only runs on the gpu-base image,
    # which always has torch; the fallback just keeps a torch-less import from crashing.
    _torch = None

_TorchModuleBase: type = _torch.nn.Module if _torch is not None else object
# `ConvStudent`/`MlpStudent` must be real *module-level* classes (not nested inside a
# function/factory) so `torch.save({"model": student_instance}, ...)` can pickle them
# by their qualified name — a nested class's pickled qualname can't be re-imported.


class ConvStudent(_TorchModuleBase):  # type: ignore[misc]
    def __init__(self, in_channels: int, base_channels: int, stages: int, num_classes: int) -> None:
        from torch import nn

        super().__init__()
        layers: list[Any] = []
        channels = in_channels
        out_channels = base_channels
        for _ in range(stages):
            layers += [
                nn.Conv2d(channels, out_channels, kernel_size=3, stride=2, padding=1),
                nn.BatchNorm2d(out_channels),
                nn.ReLU(inplace=True),
            ]
            channels = out_channels
            out_channels *= 2
        self.features = nn.Sequential(*layers)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Linear(channels, num_classes)

    def forward(self, x: Any) -> Any:
        x = self.features(x)
        x = self.pool(x).flatten(1)
        return self.classifier(x)


class MlpStudent(_TorchModuleBase):  # type: ignore[misc]
    def __init__(self, in_features: int, hidden: int, depth: int, num_classes: int) -> None:
        from torch import nn

        super().__init__()
        layers: list[Any] = []
        dim = in_features
        for _ in range(depth):
            layers += [nn.Linear(dim, hidden), nn.ReLU(inplace=True)]
            dim = hidden
        layers.append(nn.Linear(dim, num_classes))
        self.net = nn.Sequential(*layers)

    def forward(self, x: Any) -> Any:
        return self.net(x.flatten(1))


def build_student(preset: str, input_shape: tuple[int, ...], num_classes: int) -> Any:
    config = STUDENT_PRESETS.get(preset)
    if config is None:
        raise UnsupportedFormatError(
            f"student preset {preset!r} isn't wired — uploading a custom student "
            "architecture needs worker storage plumbing not built yet; pick half_width, "
            "half_depth, or compact instead"
        )
    if len(input_shape) == 4:
        return ConvStudent(input_shape[1], config["base_channels"], config["stages"], num_classes)
    in_features = int(np.prod(input_shape[1:])) if len(input_shape) > 1 else int(input_shape[0])
    return MlpStudent(in_features, config["base_channels"] * 4, config["stages"], num_classes)


def find_feature_hook_module(net: Any) -> Any | None:
    """The last `Linear` (or, failing that, last `Conv2d`) submodule — a generic,
    architecture-agnostic stand-in for "the penultimate feature layer" used to tap an
    intermediate representation on both teacher and student without knowing either
    architecture's real block structure."""
    from torch import nn

    linear_modules = [m for m in net.modules() if isinstance(m, nn.Linear)]
    if linear_modules:
        return linear_modules[-1]
    conv_modules = [m for m in net.modules() if isinstance(m, nn.Conv2d)]
    return conv_modules[-1] if conv_modules else None


class FeatureCapture:
    def __init__(self) -> None:
        self.value: Any = None

    def __call__(self, _module: Any, inputs: tuple[Any, ...]) -> None:
        self.value = inputs[0]


def attach_feature_hook(net: Any | None) -> tuple[FeatureCapture, Any] | None:
    if net is None:
        return None
    module = find_feature_hook_module(net)
    if module is None:
        return None
    capture = FeatureCapture()
    handle = module.register_forward_pre_hook(capture)
    return capture, handle


def _teacher_predict_batch(teacher_runner: Any, batch: np.ndarray) -> np.ndarray:
    """Some exported teachers (most commonly ONNX/TFLite classifiers) declare a static
    batch dimension of 1; predicting a multi-sample synthetic training batch against
    one needs a call per sample instead of one batched call."""
    try:
        result = np.asarray(teacher_runner.predict(batch))
        if result.shape[0] == batch.shape[0]:
            return result
    except Exception:  # noqa: BLE001 — fall back to per-sample inference below
        pass
    rows = [
        np.asarray(teacher_runner.predict(batch[index : index + 1])).reshape(-1)
        for index in range(batch.shape[0])
    ]
    return np.stack(rows, axis=0)


def _flatten_feature(feature: Any) -> Any:
    if feature.dim() > 2:
        return feature.mean(dim=tuple(range(2, feature.dim())))
    return feature


# ----------------------------------------------------------------------------- losses


def kd_loss(student_logits: Any, teacher_logits: Any, temp: float, alpha: float) -> Any:
    import torch.nn.functional as functional

    soft_teacher = functional.softmax(teacher_logits / temp, dim=-1)
    soft_student_log = functional.log_softmax(student_logits / temp, dim=-1)
    soft_loss = functional.kl_div(soft_student_log, soft_teacher, reduction="batchmean")
    soft_loss = soft_loss * (temp**2)

    pseudo_labels = teacher_logits.argmax(dim=-1)
    hard_loss = functional.cross_entropy(student_logits, pseudo_labels)
    return alpha * soft_loss + (1 - alpha) * hard_loss


# ------------------------------------------------------------------------------ training


def train_student(
    *,
    student: Any,
    teacher_runner: Any,
    input_shape: tuple[int, ...],
    num_classes: int,
    epochs: int,
    temp: float,
    alpha: float,
    user_id: str,
    job_id: str,
    event_repo: JobEventRepository,
    control: Any,
    feature_adapter: Any | None = None,
    teacher_capture: FeatureCapture | None = None,
    student_capture: FeatureCapture | None = None,
) -> float | None:
    """Runs `epochs` epochs of KD training on synthetic inputs sampled from the
    teacher's response surface, emitting one "Training student" `JobEvent` per epoch
    (the label `job_stages.py`'s distillation branch already declares, with the epoch
    counter `apps/api/app/services.py::_stage_dicts()` reconstructs by counting them —
    exactly one per completed epoch, matching `core.train.run_finetune_loop`'s contract).

    When `feature_adapter`/`teacher_capture`/`student_capture` are all given (feature-
    based distillation only), adds an MSE term between the student's captured
    intermediate feature (projected through `feature_adapter`) and the teacher's.
    """
    import torch

    rng = np.random.default_rng(0)
    trainable = list(student.parameters())
    if feature_adapter is not None:
        trainable += list(feature_adapter.parameters())
    optimizer = torch.optim.Adam(trainable, lr=1e-3)
    student.train()
    final_loss: float | None = None
    sample_shape = (_BATCH_SIZE, *input_shape[1:])
    has_feature_term = feature_adapter is not None and teacher_capture is not None and student_capture is not None

    for epoch in range(epochs):
        total_loss = 0.0
        for _ in range(_BATCHES_PER_EPOCH):
            batch = rng.standard_normal(sample_shape).astype(np.float32)
            with torch.no_grad():
                teacher_out = _teacher_predict_batch(teacher_runner, batch).reshape(_BATCH_SIZE, -1)
            teacher_logits = torch.as_tensor(teacher_out[:, :num_classes], dtype=torch.float32)

            optimizer.zero_grad(set_to_none=True)
            student_logits = student(torch.from_numpy(batch))
            loss = kd_loss(student_logits, teacher_logits, temp, alpha)

            if has_feature_term and teacher_capture.value is not None and student_capture.value is not None:
                teacher_feat = _flatten_feature(teacher_capture.value.detach())
                student_feat = _flatten_feature(student_capture.value)
                projected = feature_adapter(student_feat)
                if projected.shape == teacher_feat.shape:
                    feature_loss = torch.nn.functional.mse_loss(projected, teacher_feat)
                    loss = (1 - _FEATURE_LOSS_WEIGHT) * loss + _FEATURE_LOSS_WEIGHT * feature_loss

            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())

        final_loss = total_loss / _BATCHES_PER_EPOCH
        event_repo.append(
            user_id, job_id, stage="Training student",
            message=f"epoch {epoch + 1}/{epochs}, loss={final_loss:.4f}",
        )
        control.check()

    return final_loss


# --------------------------------------------------------------------------- job runner


def run_distillation_op(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    control: Any,
    event_repo: JobEventRepository,
    use_feature_matching: bool,
    job_repo: JobRepository | None = None,
    models_repo: ModelRepository | None = None,
    s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    uploads_bucket = os.environ.get("MF_UPLOADS_BUCKET", "mf-uploads")
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")

    tmpdir = tempfile.mkdtemp(prefix="mf-distill-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            uploads_bucket=uploads_bucket, results_bucket=results_bucket,
            use_feature_matching=use_feature_matching,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _setup_feature_matching(
    *, teacher_runner: Any, student: Any, model_format: str, probe: np.ndarray,
) -> tuple[Any | None, FeatureCapture | None, FeatureCapture | None, list[Any], str | None]:
    """Returns `(feature_adapter, teacher_capture, student_capture, hook_handles, note)`
    — `note` is set (and every other value `None`/empty) when feature matching can't run
    for this teacher, so the caller can report an honest reason instead of silently doing
    response-only distillation. Both hooks in `hook_handles` must stay registered for the
    whole training loop (the student's forward runs every batch), so the caller — not
    this setup step — is responsible for removing them once training finishes."""
    import torch
    from torch import nn

    teacher_module = teacher_runner.torch_module() if hasattr(teacher_runner, "torch_module") else None
    if teacher_module is None:
        return None, None, None, [], (
            "feature matching needs a traceable PyTorch/TorchScript/YOLO architecture; "
            f"a {model_format!r} teacher falls back to response-only distillation"
        )

    teacher_hook = attach_feature_hook(teacher_module)
    student_hook = attach_feature_hook(student)
    if teacher_hook is None or student_hook is None:
        for hook in (teacher_hook, student_hook):
            if hook is not None:
                hook[1].remove()
        return None, None, None, [], (
            "no matchable intermediate layer found on the teacher; fell back to "
            "response-only distillation"
        )

    teacher_capture, teacher_handle = teacher_hook
    student_capture, student_handle = student_hook
    handles = [teacher_handle, student_handle]

    with torch.no_grad():
        teacher_module(torch.from_numpy(probe))
    student(torch.from_numpy(probe))

    if teacher_capture.value is None or student_capture.value is None:
        for handle in handles:
            handle.remove()
        return None, None, None, [], (
            "the teacher's hooked layer never ran on a probe input; fell back to "
            "response-only distillation"
        )

    teacher_dim = _flatten_feature(teacher_capture.value).shape[-1]
    student_dim = _flatten_feature(student_capture.value).shape[-1]
    feature_adapter = nn.Linear(student_dim, teacher_dim)
    return feature_adapter, teacher_capture, student_capture, handles, None


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, uploads_bucket: str, results_bucket: str, use_feature_matching: bool,
) -> None:
    model = models.get(user_id, model_id)
    local_in = tmpdir / f"input{input_suffix(model.format, model.filename)}"
    local_out = tmpdir / "student.pt"

    event_repo.append(
        user_id, job_id, stage="Loading teacher", message="Downloading model from storage"
    )
    s3.download_file(uploads_bucket, model.s3_key, str(local_in))
    control.check()

    hook_handles: list[Any] = []
    try:
        event_repo.append(
            user_id, job_id, stage="Loading teacher", message="Loading teacher for inference"
        )
        teacher_runner = load_teacher_runner(model.format, local_in)
        input_shape = tuple(getattr(teacher_runner, "input_shape", _DEFAULT_IMAGE_SHAPE))
        control.check()

        event_repo.append(
            user_id, job_id, stage="Building student", message="Building student architecture"
        )
        probe = np.random.default_rng(0).standard_normal((1, *input_shape[1:])).astype(np.float32)
        teacher_probe = np.asarray(teacher_runner.predict(probe)).reshape(1, -1)
        num_classes = teacher_probe.shape[-1]
        preset = params.get("student", "half_width")
        if preset == "custom" and not params.get("student_file"):
            raise UnsupportedFormatError(
                "no student architecture file was uploaded for the 'custom' student option"
            )
        student = build_student(preset, input_shape, num_classes)

        feature_adapter = teacher_capture = student_capture = None
        feature_note: str | None = None
        if use_feature_matching:
            feature_adapter, teacher_capture, student_capture, hook_handles, feature_note = (
                _setup_feature_matching(
                    teacher_runner=teacher_runner, student=student, model_format=model.format,
                    probe=probe,
                )
            )
        control.check()

        epochs = int(params.get("epochs") or 30)
        temp = float(params.get("temp", 4))
        alpha = float(params.get("alpha", 0.7))
        train_note: str | None = None
        if params.get("train_data"):
            train_note = (
                "custom training data upload isn't wired to worker storage yet — trained on "
                "synthetic inputs sampled from the teacher's response surface instead"
            )

        final_loss = train_student(
            student=student, teacher_runner=teacher_runner, input_shape=input_shape,
            num_classes=num_classes, epochs=epochs, temp=temp, alpha=alpha, user_id=user_id,
            job_id=job_id, event_repo=event_repo, control=control, feature_adapter=feature_adapter,
            teacher_capture=teacher_capture, student_capture=student_capture,
        )
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classify framework failures for the UI
        code = "unsupported_operator" if isinstance(error, UnsupportedFormatError) else "unknown"
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=40,
            error={"code": code, "message": str(error)},
        )
        return
    finally:
        for handle in hook_handles:
            handle.remove()
    control.check()

    import torch

    event_repo.append(
        user_id, job_id, stage="Measuring accuracy", message="Comparing teacher and student outputs"
    )
    control.check()

    student.eval()
    eval_batch = np.random.default_rng(1).standard_normal((1, *input_shape[1:])).astype(np.float32)
    with torch.no_grad():
        teacher_eval = np.asarray(teacher_runner.predict(eval_batch)).reshape(1, -1)[:, :num_classes]
        student_eval = student(torch.from_numpy(eval_batch)).numpy()
    agreement_metrics = compare_arrays(teacher_eval, student_eval)

    teacher_bytes = local_in.stat().st_size
    student_param_count = sum(p.numel() for p in student.parameters())
    torch.save(
        {"model": student, "preset": preset, "input_shape": input_shape, "num_classes": num_classes},
        local_out,
    )
    student_bytes = local_out.stat().st_size

    download_name = f"{Path(model.filename).stem}_student.pt"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(local_out), results_bucket, s3_key)

    display_metrics = {
        "Student parameters": f"{student_param_count:,}",
        "File size": f"{teacher_bytes:,} bytes (teacher) -> {student_bytes:,} bytes (student)",
        "Final training loss": f"{final_loss:.4f}" if final_loss is not None else "n/a",
        **agreement_metrics,
    }
    if train_note:
        display_metrics["Training data"] = train_note
    if feature_note:
        display_metrics["Feature matching"] = feature_note

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": student_bytes,
            "downloadName": download_name,
            "metrics": display_metrics,
            "measuredOnValidation": False,
            "speedNote": None,
            "s3Key": s3_key,
        },
    )


__all__ = [
    "FeatureCapture",
    "STUDENT_PRESETS",
    "attach_feature_hook",
    "build_student",
    "find_feature_hook_module",
    "kd_loss",
    "load_teacher_runner",
    "run_distillation_op",
    "train_student",
]
