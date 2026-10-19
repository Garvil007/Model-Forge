"""q_nf4: bitsandbytes NF4 quantization — the format QLoRA fine-tuning and a quick
Transformers `load_in_4bit=True` both use. Driven by the catalog's `double`/`compute`
params (`packages/catalog/src/modelforge_catalog/methods.py`). Unlike GPTQ/AWQ, NF4
needs no calibration data: quantization happens as a side effect of
`from_pretrained(..., quantization_config=...)`, so this discards the shared runner's
already-loaded full-precision `model` (kept only for the "before" perplexity
measurement) and reloads fresh from `repo_dir` with the bitsandbytes config instead of
mutating the passed-in model in place. Modern bitsandbytes (multi-backend CPU/XPU
support) makes this runnable in `_llm_gpu_common`'s CPU test mode too, not just CUDA.
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
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    double_quant = bool(params.get("double", True))
    compute = params.get("compute", "bf16")
    compute_dtype = torch.bfloat16 if compute == "bf16" else torch.float16

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=double_quant,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    quantized = AutoModelForCausalLM.from_pretrained(
        repo_dir, quantization_config=bnb_config, device_map=device
    )
    quantized.save_pretrained(local_out)
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
        control=control, event_repo=event_repo, quantize_fn=_quantize, needs_calibration=False,
        tag="nf4", job_repo=job_repo, models_repo=models_repo,
        s3_client_override=s3_client_override,
    )


__all__ = ["run"]
