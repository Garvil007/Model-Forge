"""Real Keras model surgery for the Low-rank tab — the Keras half of the gap
`_lowrank_common.py`'s module docstring used to describe as "not implemented yet".

A target `Dense` (SVD) or plain `Conv2D` (Tucker-2/CP) layer is replaced by a chain of
smaller layers built with the Functional API and re-run through the model's existing
layer graph — every other layer is called again on its usual input, reusing its
existing (trained) weights unchanged, so the rebuilt model is a real, runnable
`tf.keras.Model`, not a raw-tensor estimate.

Scoped to `tf.keras.Sequential` models: rebuilding walks `model.layers` in order,
feeding each layer's output into the next, which is exactly `Sequential`'s own
semantics. A Functional model with branching/skip connections would need each branch's
input wired through individually — not implemented, so a non-`Sequential` model raises
`UnsupportedFormatError` rather than silently mis-wiring a branch.

Keras's `Dense` kernel is shaped `(in, units)` and `Conv2D`'s is `(kh, kw, in, out)` —
both the transpose of this module's `torch`-convention helpers in `_lowrank_common.py`
(`(out, in)` / `(out, in, kh, kw)`), so every factor is transposed/reshaped at the Keras
layer boundary before being written back with `layer.set_weights`.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ._convert_common import UnsupportedFormatError
from ._lowrank_common import (
    choose_channel_rank,
    choose_svd_rank,
    factorize_cp,
    factorize_tucker2,
    is_attention_name,
)


def _rebuild_sequential(
    model: Any, build_replacement: Any
) -> tuple[Any, list[dict[str, Any]]]:
    import tensorflow as tf

    if not isinstance(model, tf.keras.Sequential):
        raise UnsupportedFormatError(
            "real Keras low-rank surgery only supports tf.keras.Sequential models; a "
            "branching Functional model needs each branch's input wiring threaded "
            "through individually, which isn't implemented (see _lowrank_keras.py's "
            "module docstring)"
        )

    inputs = model.inputs
    if len(inputs) != 1:
        raise UnsupportedFormatError("real Keras low-rank surgery needs exactly one model input")

    x = inputs[0]
    reports: list[dict[str, Any]] = []
    for layer in model.layers:
        x, report = build_replacement(layer, x)
        if report is not None:
            reports.append(report)

    new_model = tf.keras.Model(inputs=inputs, outputs=x, name=f"{model.name}_lowrank")
    return new_model, reports


# -------------------------------------------------------------------------------- SVD


def keras_svd_decompose(model: Any, params: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    import tensorflow as tf

    mode = params.get("mode", "energy")
    energy_pct = float(params.get("energy", 95))
    rank_pct = float(params.get("rank", 25))
    layers_filter = params.get("layers", "mlp")

    def _build(layer: Any, x: Any) -> tuple[Any, dict[str, Any] | None]:
        if not isinstance(layer, tf.keras.layers.Dense):
            return layer(x), None
        if layers_filter == "mlp" and is_attention_name(layer.name):
            return layer(x), None

        kernel = layer.get_weights()[0]  # (in, units)
        in_dim, out_dim = kernel.shape
        params_before = in_dim * out_dim
        singular_values = np.linalg.svd(kernel.astype(np.float64), compute_uv=False)
        rank = choose_svd_rank(singular_values, mode, energy_pct, rank_pct)
        params_after = rank * (in_dim + out_dim)

        if params_after >= params_before:
            report = {
                "name": layer.name, "shape": (out_dim, in_dim), "rank": rank,
                "params_before": params_before, "params_after": params_before, "skipped": True,
            }
            return layer(x), report

        u, s, vt = np.linalg.svd(kernel.astype(np.float64), full_matrices=False)
        scale = np.sqrt(s[:rank])
        factor_a = (u[:, :rank] * scale).astype(kernel.dtype)  # (in, rank)
        factor_b = (scale[:, None] * vt[:rank, :]).astype(kernel.dtype)  # (rank, out)

        layer_a = tf.keras.layers.Dense(rank, use_bias=False, name=f"{layer.name}_svd_a")
        layer_b = tf.keras.layers.Dense(
            out_dim, use_bias=layer.use_bias, activation=layer.activation,
            name=f"{layer.name}_svd_b",
        )
        new_x = layer_a(x)
        new_x = layer_b(new_x)
        layer_a.set_weights([factor_a])
        weights_b = [factor_b] + (layer.get_weights()[1:] if layer.use_bias else [])
        layer_b.set_weights(weights_b)

        report = {
            "name": layer.name, "shape": (out_dim, in_dim), "rank": rank,
            "params_before": params_before, "params_after": params_after, "skipped": False,
        }
        return new_x, report

    return _rebuild_sequential(model, _build)


# ---------------------------------------------------------------------- Tucker-2 / CP


def keras_conv_decompose(model: Any, params: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    import tensorflow as tf

    kind = params.get("kind", "tucker2")
    rank_pct = float(params.get("rank", 30))

    def _build(layer: Any, x: Any) -> tuple[Any, dict[str, Any] | None]:
        if not isinstance(layer, tf.keras.layers.Conv2D) or layer.groups != 1:
            return layer(x), None

        kernel = layer.get_weights()[0]  # (kh, kw, in, out)
        kh, kw, in_ch, out_ch = kernel.shape
        params_before = out_ch * in_ch * kh * kw
        # torch-convention (out, in, kh, kw), matching _lowrank_common's factorize_* helpers.
        weight_torch = kernel.transpose(3, 2, 0, 1)

        if kind == "cp":
            rank = max(1, min(out_ch, in_ch, round(min(out_ch, in_ch) * rank_pct / 100)))
            params_after = rank * (out_ch + in_ch + kh + kw)
        else:
            rank_out = choose_channel_rank(out_ch, rank_pct)
            rank_in = choose_channel_rank(in_ch, rank_pct)
            params_after = rank_out * rank_in * kh * kw + out_ch * rank_out + in_ch * rank_in

        if params_after >= params_before:
            report = {
                "name": layer.name, "shape": (out_ch, in_ch, kh, kw),
                "rank": rank if kind == "cp" else f"{rank_out}x{rank_in}",
                "params_before": params_before, "params_after": params_before, "skipped": True,
            }
            return layer(x), report

        bias = layer.get_weights()[1:] if layer.use_bias else []

        if kind == "cp":
            weights, factor_out, factor_in, factor_kh, factor_kw = factorize_cp(
                weight_torch, rank
            )
            factor_out_scaled = (factor_out * weights[None, :]).astype(kernel.dtype)

            conv_in = tf.keras.layers.Conv2D(
                rank, 1, use_bias=False, name=f"{layer.name}_cp_in"
            )
            conv_kh = tf.keras.layers.Conv2D(
                rank, (kh, 1), strides=(layer.strides[0], 1), padding=layer.padding,
                dilation_rate=(layer.dilation_rate[0], 1), groups=rank, use_bias=False,
                name=f"{layer.name}_cp_kh",
            )
            conv_kw = tf.keras.layers.Conv2D(
                rank, (1, kw), strides=(1, layer.strides[1]), padding=layer.padding,
                dilation_rate=(1, layer.dilation_rate[1]), groups=rank, use_bias=False,
                name=f"{layer.name}_cp_kw",
            )
            conv_out = tf.keras.layers.Conv2D(
                out_ch, 1, use_bias=layer.use_bias, activation=layer.activation,
                name=f"{layer.name}_cp_out",
            )

            new_x = conv_in(x)
            new_x = conv_kh(new_x)
            new_x = conv_kw(new_x)
            new_x = conv_out(new_x)

            conv_in.set_weights([factor_in.reshape(1, 1, in_ch, rank).astype(kernel.dtype)])
            conv_kh.set_weights([factor_kh.reshape(kh, 1, 1, rank).astype(kernel.dtype)])
            conv_kw.set_weights([factor_kw.reshape(1, kw, 1, rank).astype(kernel.dtype)])
            conv_out.set_weights(
                [factor_out_scaled.T.reshape(1, 1, rank, out_ch).astype(kernel.dtype)] + bias
            )
            rank_report: Any = rank
        else:
            core, factor_out, factor_in = factorize_tucker2(weight_torch, rank_out, rank_in)

            conv_in = tf.keras.layers.Conv2D(
                rank_in, 1, use_bias=False, name=f"{layer.name}_tucker_in"
            )
            conv_core = tf.keras.layers.Conv2D(
                rank_out, (kh, kw), strides=layer.strides, padding=layer.padding,
                dilation_rate=layer.dilation_rate, use_bias=False, name=f"{layer.name}_tucker_core",
            )
            conv_out = tf.keras.layers.Conv2D(
                out_ch, 1, use_bias=layer.use_bias, activation=layer.activation,
                name=f"{layer.name}_tucker_out",
            )

            new_x = conv_in(x)
            new_x = conv_core(new_x)
            new_x = conv_out(new_x)

            conv_in.set_weights([factor_in.reshape(in_ch, rank_in, 1, 1).transpose(2, 3, 0, 1)])
            conv_core.set_weights([core.transpose(2, 3, 1, 0).astype(kernel.dtype)])
            conv_out.set_weights(
                [factor_out.reshape(out_ch, rank_out, 1, 1).transpose(2, 3, 1, 0)] + bias
            )
            rank_report = f"{rank_out}x{rank_in}"

        report = {
            "name": layer.name, "shape": (out_ch, in_ch, kh, kw), "rank": rank_report,
            "params_before": params_before, "params_after": params_after, "skipped": False,
        }
        return new_x, report

    return _rebuild_sequential(model, _build)


__all__ = ["keras_conv_decompose", "keras_svd_decompose"]
