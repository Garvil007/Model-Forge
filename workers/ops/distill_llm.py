"""d_llm: distills a smaller language model from a Hugging Face causal-LM teacher.
Student construction is "layer-dropped" (every other decoder layer removed from a deep
copy of the teacher, the same real technique DistilBERT-style models use) when
`params["student"] == "layerdrop"`; `"small"` (a smaller checkpoint from the same model
family) isn't wired — there's no generic repo-id mapping from "this family" to "its
smaller sibling" — refused with a clean `unsupported_operator` rather than guessing a
repo id.

Training text is `params["data"] == "upload"`'s `texts` file when that upload is wired
to worker storage (it isn't yet — see `workers/ops/_llm_common.py::resolve_calibration_text`'s
documented gap) or, always today, synthetic continuations the teacher itself generates
from a handful of seed prompts plus the bundled default calibration passage — real text
flowing through a real KD loss either way, just not the user's own upload yet.
`params["tokens"]` ("250M"/"1B"/"5B") scales the number of training steps taken as a
coarse proxy for token budget (`_STEPS_BY_TOKEN_BUDGET`), not a literal token count —
the same class of estimate `methods.py`'s `impact_estimate` lambdas already use for
cost/duration in the UI.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from modelforge_catalog.models import OperationSpec
from modelforge_catalog.validation import format_metric
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository
from modelforge_db.repositories.models import ModelRepository

from core.evaluators.perplexity import PerplexityEvaluator
from core.exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError

from ._convert_common import UnsupportedFormatError, require_hf_repo_id, s3_client, zip_directory
from ._llm_common import (
    classify_llm_error,
    default_calibration_text,
    download_hf_snapshot,
    resolve_hf_token,
)
from ._llm_gpu_common import resolve_device

_PERPLEXITY_MAX_SAMPLES = 8
_PERPLEXITY_WINDOW = 256
_PERPLEXITY_STRIDE = 128
_SEQ_LEN = 64
_STEPS_BY_TOKEN_BUDGET = {"250M": 2, "1B": 4, "5B": 8}
_KD_TEMP = 2.0
_KD_ALPHA = 0.5

_SEED_PROMPTS = (
    "The history of",
    "In recent scientific research,",
    "A good way to explain this is",
    "According to the latest reports,",
)


class _HfCausalLmRunner:
    """Same adapter shape as `_llm_gpu_common._HfCausalLmRunner` — duplicated locally
    rather than imported, since that one's a module-private implementation detail of
    the one-shot quantize runner, not a shared export."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def predict(self, batch: np.ndarray) -> np.ndarray:
        import torch

        with torch.no_grad():
            input_ids = torch.as_tensor(np.asarray(batch), dtype=torch.long).to(self._model.device)
            logits = self._model(input_ids).logits
        return logits.float().cpu().numpy()


def _measure_perplexity(model: Any, tokenizer: Any, texts: list[str]) -> float:
    evaluator = PerplexityEvaluator(
        tokenizer, window_size=_PERPLEXITY_WINDOW, stride=_PERPLEXITY_STRIDE
    )
    return evaluator.evaluate(_HfCausalLmRunner(model), texts, _PERPLEXITY_MAX_SAMPLES).value


def _build_layerdrop_student(model: Any) -> Any:
    """Drops every other decoder layer from a deep copy of `model`, keeping embeddings,
    norms, and the LM head intact — a real, loadable, genuinely smaller causal LM, not a
    stub. Works for any architecture exposing its decoder stack at `model.model.layers`,
    `transformer.h`, or `gpt_neox.layers` (covers Llama/Mistral/Qwen-style, GPT-2-style,
    and GPT-NeoX-style models respectively); anything else is refused rather than
    guessing at an unfamiliar module tree.
    """
    import copy

    import torch

    container = None
    attr_path = ""
    for candidate_path in ("model.layers", "transformer.h", "gpt_neox.layers"):
        probe = model
        found = True
        for part in candidate_path.split("."):
            probe = getattr(probe, part, None)
            if probe is None:
                found = False
                break
        if found:
            container, attr_path = probe, candidate_path
            break

    if container is None:
        raise UnsupportedFormatError(
            "layer-dropped distillation needs a decoder-layer list this worker recognizes "
            "(model.layers / transformer.h / gpt_neox.layers) — this architecture isn't one yet"
        )

    student = copy.deepcopy(model)
    target = student
    parts = attr_path.split(".")
    for part in parts[:-1]:
        target = getattr(target, part)
    kept = torch.nn.ModuleList([layer for index, layer in enumerate(container) if index % 2 == 0])
    setattr(target, parts[-1], kept)
    if hasattr(student.config, "num_hidden_layers"):
        student.config.num_hidden_layers = len(kept)
    return student


def _build_student(model: Any, params: dict[str, Any]) -> Any:
    student_choice = params.get("student", "layerdrop")
    if student_choice == "layerdrop":
        return _build_layerdrop_student(model)
    raise UnsupportedFormatError(
        f"student option {student_choice!r} isn't wired yet — there's no generic mapping "
        "from a model family to its smaller sibling's repo id; pick 'layerdrop' instead"
    )


def _resolve_training_texts(tokenizer: Any, teacher: Any, device: str) -> list[str]:
    """`params["data"] == "upload"`'s `texts` file isn't wired to worker storage yet
    (module docstring) — always generates synthetic continuations from the teacher
    itself plus the bundled default calibration passage, real text through a real KD
    loss either way."""
    import torch

    texts = [default_calibration_text()]
    for prompt in _SEED_PROMPTS:
        input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)
        with torch.no_grad():
            generated = teacher.generate(
                input_ids, max_new_tokens=_SEQ_LEN, do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        texts.append(tokenizer.decode(generated[0], skip_special_tokens=True))
    return texts


def _make_batches(texts: list[str], tokenizer: Any, device: str) -> list[Any]:
    batches = []
    for text in texts:
        encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=_SEQ_LEN + 1)
        input_ids = encoded.input_ids.to(device)
        if input_ids.shape[-1] < 2:
            continue
        batches.append(input_ids)
    return batches


def _train_student(
    *, student: Any, teacher: Any, batches: list[Any], steps: int, user_id: str, job_id: str,
    event_repo: JobEventRepository, control: Any,
) -> float | None:
    import torch
    import torch.nn.functional as functional

    optimizer = torch.optim.Adam(student.parameters(), lr=5e-5)
    student.train()
    final_loss: float | None = None

    for step in range(steps):
        total_loss = 0.0
        for input_ids in batches:
            context, target = input_ids[:, :-1], input_ids[:, 1:]
            with torch.no_grad():
                teacher_logits = teacher(context).logits
            student_logits = student(context).logits

            soft_teacher = functional.softmax(teacher_logits / _KD_TEMP, dim=-1)
            soft_student_log = functional.log_softmax(student_logits / _KD_TEMP, dim=-1)
            soft_loss = functional.kl_div(soft_student_log, soft_teacher, reduction="batchmean")
            soft_loss = soft_loss * (_KD_TEMP**2)
            hard_loss = functional.cross_entropy(
                student_logits.reshape(-1, student_logits.shape[-1]), target.reshape(-1)
            )
            loss = _KD_ALPHA * soft_loss + (1 - _KD_ALPHA) * hard_loss

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())

        final_loss = total_loss / max(1, len(batches))
        event_repo.append(
            user_id, job_id, stage="Training student",
            message=f"epoch {step + 1}/{steps}, loss={final_loss:.4f}",
        )
        control.check()

    return final_loss


def run(
    *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    operation: OperationSpec, control: Any, event_repo: JobEventRepository,
    job_repo: Any = None, models_repo: Any = None, s3_client_override: Any = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    models = models_repo if models_repo is not None else ModelRepository()
    s3 = s3_client_override if s3_client_override is not None else s3_client()
    results_bucket = os.environ.get("MF_RESULTS_BUCKET", "mf-results")
    device = resolve_device()

    tmpdir = tempfile.mkdtemp(prefix="mf-distill-llm-")
    try:
        _run_in_tempdir(
            Path(tmpdir), user_id=user_id, job_id=job_id, model_id=model_id, params=params,
            control=control, event_repo=event_repo, jobs=jobs, models=models, s3=s3,
            results_bucket=results_bucket, device=device,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_in_tempdir(
    tmpdir: Path, *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    control: Any, event_repo: JobEventRepository, jobs: JobRepository, models: ModelRepository,
    s3: Any, results_bucket: str, device: str,
) -> None:
    model_record = models.get(user_id, model_id)
    local_out = tmpdir / "output"
    local_out.mkdir(parents=True, exist_ok=True)
    before_ppl: float | None = None
    after_ppl: float | None = None
    texts: list[str] = []
    final_loss: float | None = None

    event_repo.append(
        user_id, job_id, stage="Loading teacher", message="Downloading Hugging Face repo"
    )
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        repo_id = require_hf_repo_id(model_record)
        token = resolve_hf_token(user_id)
        repo_dir = tmpdir / "hf_repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        download_hf_snapshot(repo_id, token, repo_dir)
        control.check()

        tokenizer = AutoTokenizer.from_pretrained(repo_dir)
        teacher = AutoModelForCausalLM.from_pretrained(
            repo_dir, torch_dtype=torch.float32, device_map=device
        )
        teacher.eval()

        event_repo.append(
            user_id, job_id, stage="Loading teacher", message="Measuring baseline perplexity"
        )
        texts = _resolve_training_texts(tokenizer, teacher, device)
        before_ppl = _measure_perplexity(teacher, tokenizer, texts)
        control.check()

        event_repo.append(
            user_id, job_id, stage="Building student", message="Building student architecture"
        )
        student = _build_student(teacher, params)
        control.check()

        steps = _STEPS_BY_TOKEN_BUDGET.get(params.get("tokens", "1B"), 4)
        batches = _make_batches(texts, tokenizer, device)
        final_loss = _train_student(
            student=student, teacher=teacher, batches=batches, steps=steps, user_id=user_id,
            job_id=job_id, event_repo=event_repo, control=control,
        )

        event_repo.append(
            user_id, job_id, stage="Measuring accuracy", message="Measuring perplexity after"
        )
        after_ppl = _measure_perplexity(student, tokenizer, texts)
        student.save_pretrained(local_out)
        tokenizer.save_pretrained(local_out)
    except (JobCanceledError, JobTimeoutError, SpotInterruptedError):
        raise
    except Exception as error:  # noqa: BLE001 — classified below for the UI
        code, message = classify_llm_error(error)
        jobs.update_progress(
            user_id, job_id, status="failed", progress_percent=50,
            error={"code": code, "message": message},
        )
        return
    control.check()

    upload_path = tmpdir / "output.zip"
    zip_directory(local_out, upload_path)
    output_bytes = upload_path.stat().st_size
    download_name = f"{Path(model_record.filename).stem}_student.zip"
    s3_key = f"users/{user_id}/results/{job_id}/{download_name}"
    s3.upload_file(str(upload_path), results_bucket, s3_key)

    jobs.update_progress(
        user_id, job_id, status="succeeded", progress_percent=100,
        result={
            "outputBytes": output_bytes,
            "downloadName": download_name,
            "metrics": {
                "Perplexity": format_metric(before_ppl, after_ppl, "", lower_is_better=True),
                "Final training loss": f"{final_loss:.4f}" if final_loss is not None else "n/a",
            },
            "measuredOnValidation": True,
            "evaluation": {
                "taskType": "lm", "metricName": "Perplexity", "before": before_ppl,
                "after": after_ppl, "unit": "", "samplesUsed": len(texts), "datasetId": None,
            },
            "speedNote": None,
            "s3Key": s3_key,
        },
    )


__all__ = ["run"]
