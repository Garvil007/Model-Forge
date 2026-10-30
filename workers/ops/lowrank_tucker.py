"""l_tucker: Tucker-2 or CP decomposition of Conv2d kernels via `tensorly`. Tucker-2
decomposes only the output/input channel modes of a `(out, in, kh, kw)` kernel, leaving
the spatial modes full — stable and the recommended default. CP (canonical polyadic)
decomposes all four modes into a rank-R sum of outer products — smaller at the same
rank, harder to recover accuracy from without fine-tuning, matching the catalog's own
framing (`packages/catalog/src/modelforge_catalog/methods.py`'s `l_tucker` entry).

Layers where the decomposition wouldn't actually save parameters at the requested rank
are left untouched and reported as skipped. `torch`/`safetensors` factor the raw tensor
dict in place (`_lowrank_common.apply_tucker_to_tensors`); `onnx` rewrites each plain
`Conv` node into a chain of smaller `Conv` nodes (`_lowrank_onnx.onnx_conv_decompose`);
`keras` rebuilds each target `Conv2D` layer the same way with real layers
(`_lowrank_keras.keras_conv_decompose`, `Sequential` models only). `finetune` always
degrades to a clean, noted skip — see `_lowrank_common.py`'s module docstring.
"""

from __future__ import annotations

from typing import Any

from ._lowrank_common import apply_tucker_to_tensors, run_lowrank_op
from ._lowrank_keras import keras_conv_decompose
from ._lowrank_onnx import onnx_conv_decompose


def run(**kwargs: Any) -> None:
    run_lowrank_op(
        tensor_decompose_fn=apply_tucker_to_tensors,
        onnx_decompose_fn=onnx_conv_decompose,
        keras_decompose_fn=keras_conv_decompose,
        download_name_tag="tucker",
        **kwargs,
    )


__all__ = ["run"]
