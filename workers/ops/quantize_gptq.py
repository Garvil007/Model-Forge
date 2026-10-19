"""q_gptq: GPTQ quantization via llm-compressor's `GPTQModifier` — layer-by-layer
weight quantization with error correction, driven by the catalog's `bits`/`group`/
`dataset`/`act_order` params (`packages/catalog/src/modelforge_catalog/methods.py`).
Orchestration (download, baseline/post perplexity, upload, error classification) lives
in `_llm_gpu_common.run_llm_gpu_quantize`; this module only supplies the quantization
step itself, run on whatever `device` that shared runner resolves (real `gpu-base` image:
CUDA; tests: `MF_LLM_DEVICE=cpu`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from ._llm_gpu_common import run_llm_gpu_quantize


def _quantize(
    model: Any, tokenizer: Any, repo_dir: Path, local_out: Path, params: dict[str, Any],
    device: str, calibration_texts: list[str],
) -> None:
    import datasets as hf_datasets
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import GPTQModifier

    bits = int(params.get("bits", "4"))
    group_size = int(params.get("group", "128"))
    act_order = bool(params.get("act_order", True))

    recipe = GPTQModifier(
        targets="Linear",
        scheme=f"W{bits}A16",
        group_size=group_size,
        actorder="weight" if act_order else None,
        ignore=["lm_head"],
    )
    calibration_dataset = hf_datasets.Dataset.from_dict({"text": calibration_texts})

    oneshot(
        model=model,
        tokenizer=tokenizer,
        dataset=calibration_dataset,
        recipe=recipe,
        max_seq_length=512,
        num_calibration_samples=len(calibration_texts),
    )
    model.save_pretrained(local_out, save_compressed=True)
    tokenizer.save_pretrained(local_out)


def run(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    job_repo: Any = None,
    models_repo: Any = None,
    s3_client_override: Any = None,
) -> None:
    run_llm_gpu_quantize(
        user_id=user_id, job_id=job_id, model_id=model_id, params=params, operation=operation,
        control=control, event_repo=event_repo, quantize_fn=_quantize, needs_calibration=True,
        tag=f"gptq-{params.get('bits', '4')}bit", job_repo=job_repo, models_repo=models_repo,
        s3_client_override=s3_client_override,
    )


__all__ = ["run"]
