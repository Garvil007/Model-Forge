"""p_wanda: one-shot LLM pruning (Wanda or SparseGPT) via llm-compressor's pruning
modifiers — same shared GPU-LLM runner `quantize_gptq.py` uses
(`_llm_gpu_common.run_llm_gpu_quantize`: download repo, load with Transformers, measure
baseline perplexity, hand off to this module's `_prune` for the actual one-shot pass,
reload the result, measure perplexity after, zip, upload), just swapping the
`GPTQModifier` for a pruning modifier and skipping the calibration-stage event (Wanda/
SparseGPT don't need a separate calibration pass the way GPTQ's error-correction does —
`needs_calibration=False`, matching `job_stages.py`'s pruning branch, which never adds
a calibration stage regardless of technique).

`pattern="2:4"` sets `sparsity_structure="2:4"` on the modifier (GPU sparse-tensor-core
speedup, no `sparsity` param needed — it's always exactly half); `pattern="unstructured"`
uses the catalog's `sparsity` param directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from ._llm_gpu_common import run_llm_gpu_quantize


def _prune(
    model: Any, tokenizer: Any, repo_dir: Path, local_out: Path, params: dict[str, Any],
    device: str, calibration_texts: list[str],
) -> None:
    import datasets as hf_datasets
    from llmcompressor import oneshot
    from llmcompressor.modifiers.pruning import SparseGPTModifier, WandaPruningModifier

    algo = params.get("algo", "wanda")
    pattern = params.get("pattern", "unstructured")
    sparsity = float(params.get("sparsity", 50)) / 100

    modifier_kwargs: dict[str, Any] = {"targets": "Linear", "ignore": ["lm_head"]}
    if pattern == "2:4":
        modifier_kwargs["sparsity_structure"] = "2:4"
        modifier_kwargs["sparsity"] = 0.5
    else:
        modifier_kwargs["sparsity"] = sparsity

    modifier = (
        SparseGPTModifier(**modifier_kwargs)
        if algo == "sparsegpt"
        else WandaPruningModifier(**modifier_kwargs)
    )

    calibration_dataset = hf_datasets.Dataset.from_dict({"text": calibration_texts})
    oneshot(
        model=model, tokenizer=tokenizer, dataset=calibration_dataset, recipe=modifier,
        max_seq_length=512, num_calibration_samples=len(calibration_texts),
    )
    model.save_pretrained(local_out, save_compressed=True)
    tokenizer.save_pretrained(local_out)


def run(
    *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    operation: OperationSpec, control: Any, event_repo: JobEventRepository,
    job_repo: Any = None, models_repo: Any = None, s3_client_override: Any = None,
) -> None:
    algo = params.get("algo", "wanda")
    pattern = params.get("pattern", "unstructured")
    tag = f"{algo}-{pattern.replace(':', '')}"
    run_llm_gpu_quantize(
        user_id=user_id, job_id=job_id, model_id=model_id, params=params, operation=operation,
        control=control, event_repo=event_repo, quantize_fn=_prune, needs_calibration=False,
        tag=tag, job_repo=job_repo, models_repo=models_repo, s3_client_override=s3_client_override,
    )


__all__ = ["run"]
