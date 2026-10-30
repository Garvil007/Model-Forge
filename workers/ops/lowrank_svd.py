"""l_svd: truncated SVD factorization of Linear/Dense weight matrices — replaces each
`(out, in)` weight tensor with two smaller ones, `(out, rank)` and `(rank, in)`, whose
product approximates the original. Rank is chosen either by the share of singular-value
energy to keep or by a fixed fraction of the matrix's max rank; layers where factorizing
wouldn't actually save parameters (`rank * (out + in) >= out * in`, which happens at
high energy on a near-square or already-thin matrix) are left untouched and reported as
skipped rather than silently bloating the file.

`layers="mlp"` restricts factorization to feed-forward/dense weights (anything whose
name doesn't look like an attention projection, via `_lowrank_common.is_attention_name`);
`layers="attn"` factorizes both. `torch`/`safetensors` factor the raw tensor dict in
place (`_lowrank_common.apply_svd_to_tensors`); `onnx` rewrites `Gemm`/`MatMul` nodes
into two chained `MatMul`s (`_lowrank_onnx.onnx_svd_decompose`); `keras` rebuilds each
target `Dense` layer as two smaller `Dense` layers (`_lowrank_keras.keras_svd_decompose`).
`finetune` always degrades to a clean, noted skip — see `_lowrank_common.py`'s module
docstring.
"""

from __future__ import annotations

from typing import Any

from ._lowrank_common import apply_svd_to_tensors, run_lowrank_op
from ._lowrank_keras import keras_svd_decompose
from ._lowrank_onnx import onnx_svd_decompose


def run(**kwargs: Any) -> None:
    run_lowrank_op(
        tensor_decompose_fn=apply_svd_to_tensors,
        onnx_decompose_fn=onnx_svd_decompose,
        keras_decompose_fn=keras_svd_decompose,
        download_name_tag="svd",
        **kwargs,
    )


__all__ = ["run"]
