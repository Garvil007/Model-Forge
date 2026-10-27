"""l_svd: truncated SVD factorization of Linear/Dense weight matrices — replaces each
`(out, in)` weight tensor with two smaller ones, `(out, rank)` and `(rank, in)`, whose
product approximates the original. Rank is chosen either by the share of singular-value
energy to keep or by a fixed fraction of the matrix's max rank; layers where factorizing
wouldn't actually save parameters (`rank * (out + in) >= out * in`, which happens at
high energy on a near-square or already-thin matrix) are left untouched and reported as
skipped rather than silently bloating the file.

`layers="mlp"` restricts factorization to feed-forward/dense weights (anything whose
name doesn't look like an attention projection, via `_lowrank_common.is_attention_name`);
`layers="attn"` factorizes both. Works directly on raw tensors via
`_lowrank_common.require_raw_tensor_format`/`load_raw_tensors`/`save_raw_tensors` — see
`_lowrank_common.py`'s module docstring for why only `torch`/`safetensors` are
implemented (ONNX/Keras would need real graph/model surgery) and why `finetune` always
degrades to a clean, noted skip.
"""

from __future__ import annotations

from typing import Any

from ._lowrank_common import apply_svd_to_tensors, run_lowrank_op


def run(**kwargs: Any) -> None:
    run_lowrank_op(decompose_fn=apply_svd_to_tensors, download_name_tag="svd", **kwargs)


__all__ = ["run"]
