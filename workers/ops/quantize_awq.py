"""q_awq: activation-aware quantization via llm-compressor's `AWQModifier` — protects
the weights whose activations matter most, driven by the catalog's `group`/`kernel`
params (`packages/catalog/src/modelforge_catalog/methods.py`). `kernel` (GEMM for
batched serving, GEMV for single-request latency) is recorded into the saved
`quantization_config` so Transformers/vLLM pick the matching inference kernel, not
something this quantization step itself needs to branch on. Orchestration lives in
`_llm_gpu_common.run_llm_gpu_quantize`, same as `quantize_gptq.py`.
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
    from llmcompressor.modifiers.awq import AWQModifier

    group_size = int(params.get("group", "128"))
    kernel = params.get("kernel", "gemm")

    recipe = AWQModifier(
        targets="Linear",
        scheme="W4A16",
        group_size=group_size,
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

    # Record the kernel choice for Transformers/vLLM's inference-time kernel selection —
    # the quantization step itself doesn't branch on gemm vs. gemv, only serving does.
    config_path = local_out / "config.json"
    if config_path.exists():
        import json

        config = json.loads(config_path.read_text(encoding="utf-8"))
        config.setdefault("quantization_config", {})["version"] = kernel
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


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
        tag=f"awq-{params.get('kernel', 'gemm')}", job_repo=job_repo, models_repo=models_repo,
        s3_client_override=s3_client_override,
    )


__all__ = ["run"]
