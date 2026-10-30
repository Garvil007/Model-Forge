"""Real ONNX graph surgery for the Low-rank tab — the ONNX half of the gap
`_lowrank_common.py`'s module docstring used to describe as "not implemented yet".

SVD (`onnx_svd_decompose`): a `Gemm`/`MatMul` node whose weight input is a 2-D
initializer consumed by exactly one node is replaced in place by two chained `MatMul`
nodes (plus the original bias `Add`, if any) — `Y = A @ V^T @ U^T (+ C)` instead of
`Y = A @ W^T (+ C)`, where `W ≈ U @ V` is the truncated-SVD approximation. Only the
common export shape is supported: `Gemm` with `transA=0, transB=1, alpha=1, beta=1`
(the shape `torch.onnx.export` of an `nn.Linear` produces), or a bare `MatMul` with the
weight stored as `(in, out)`. A `Gemm`/`MatMul` whose attributes don't match, or whose
weight initializer is shared by more than one node, is left untouched and reported as
skipped rather than guessed at.

Tucker-2/CP (`onnx_conv_decompose`): a `Conv` node (`group=1`, 2-D, weight consumed by
exactly one node) is replaced by a chain of smaller `Conv` nodes carrying the original
node's `strides`/`pads`/`dilations`:
- Tucker-2: `1x1 (in -> rank_in)` -> `kh x kw (rank_in -> rank_out, same conv attrs as
  the original)` -> `1x1 (rank_out -> out)`.
- CP: `1x1 (in -> rank)` -> `kh x 1, group=rank (depthwise)` -> `1 x kw, group=rank
  (depthwise)` -> `1x1 (rank -> out)`.
The original node's bias (if any) is added once, after the last 1x1 convolution, via a
single `Add`. The rewritten graph is directly runnable through `onnxruntime` — no
external architecture required, unlike the `torch`/`safetensors` raw-tensor path.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ._lowrank_common import (
    choose_channel_rank,
    choose_svd_rank,
    factorize_cp,
    factorize_tucker2,
    is_attention_name,
)


def _attr(node: Any, name: str, default: Any) -> Any:
    import onnx

    for attribute in node.attribute:
        if attribute.name == name:
            return onnx.helper.get_attribute_value(attribute)
    return default


def _single_consumer_weight_nodes(graph: Any, op_types: tuple[str, ...]) -> dict[str, int]:
    """Maps a weight initializer's name to the single node index that consumes it as
    its second input — only initializers consumed by exactly one `op_types` node are
    candidates; a weight shared by more than one node is left alone (ambiguous which
    node's shape the replacement should follow)."""
    initializer_names = {init.name for init in graph.initializer}
    consumers: dict[str, list[int]] = {}
    for idx, node in enumerate(graph.node):
        if node.op_type in op_types and len(node.input) >= 2 and node.input[1] in initializer_names:
            consumers.setdefault(node.input[1], []).append(idx)
    return {name: indices[0] for name, indices in consumers.items() if len(indices) == 1}


def _replace_nodes(graph: Any, replacements: dict[int, list[Any]]) -> None:
    """Splices `replacements[idx]` in at node `idx`'s original position — ONNX runtimes
    expect (and the spec recommends) topologically ordered nodes, so new nodes go where
    the one they replace used to be, not appended at the end."""
    kept = []
    for idx, node in enumerate(graph.node):
        kept.extend(replacements.get(idx, [node]))
    del graph.node[:]
    graph.node.extend(kept)


# -------------------------------------------------------------------------------- SVD


def onnx_svd_decompose(model: Any, params: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    import onnx
    from onnx import numpy_helper

    mode = params.get("mode", "energy")
    energy_pct = float(params.get("energy", 95))
    rank_pct = float(params.get("rank", 25))
    layers = params.get("layers", "mlp")

    graph = model.graph
    initializers = {init.name: init for init in graph.initializer}
    candidates = _single_consumer_weight_nodes(graph, ("Gemm", "MatMul"))

    replacements: dict[int, list[Any]] = {}
    new_initializers: list[Any] = []
    removed_initializers: set[str] = set()
    reports: list[dict[str, Any]] = []

    for weight_name, idx in candidates.items():
        node = graph.node[idx]
        weight_array = numpy_helper.to_array(initializers[weight_name])
        if weight_array.ndim != 2 or not np.issubdtype(weight_array.dtype, np.floating):
            continue
        if layers == "mlp" and is_attention_name(weight_name):
            continue

        bias_name: str | None = None
        if node.op_type == "Gemm":
            trans_a, trans_b = _attr(node, "transA", 0), _attr(node, "transB", 0)
            alpha, beta = _attr(node, "alpha", 1.0), _attr(node, "beta", 1.0)
            if trans_a != 0 or trans_b != 1 or alpha != 1.0 or beta != 1.0:
                continue  # unsupported Gemm attribute combination; leave untouched
            weight_out_in = weight_array  # transB=1 -> stored as (out, in) already
            if len(node.input) > 2 and node.input[2]:
                bias_name = node.input[2]
        else:
            weight_out_in = weight_array.T  # MatMul stores B as (in, out)

        out_dim, in_dim = weight_out_in.shape
        params_before = out_dim * in_dim
        singular_values = np.linalg.svd(weight_out_in.astype(np.float64), compute_uv=False)
        rank = choose_svd_rank(singular_values, mode, energy_pct, rank_pct)
        params_after = rank * (out_dim + in_dim)

        if params_after >= params_before:
            reports.append({
                "name": weight_name, "shape": (out_dim, in_dim), "rank": rank,
                "params_before": params_before, "params_after": params_before, "skipped": True,
            })
            continue

        u, s, vt = np.linalg.svd(weight_out_in.astype(np.float64), full_matrices=False)
        scale = np.sqrt(s[:rank])
        u_t = (u[:, :rank] * scale).T.astype(weight_array.dtype).copy()  # (rank, out)
        v_t = (scale[:, None] * vt[:rank, :]).T.astype(weight_array.dtype).copy()  # (in, rank)

        v_t_name, u_t_name = f"{weight_name}__lowrank_vT", f"{weight_name}__lowrank_uT"
        mid_name = f"{node.output[0]}__lowrank_mid"
        final_name = node.output[0] if bias_name is None else f"{node.output[0]}__lowrank_premerge"
        base_name = node.name or weight_name

        new_nodes = [
            onnx.helper.make_node(
                "MatMul", [node.input[0], v_t_name], [mid_name], name=f"{base_name}__lowrank_mm1"
            ),
            onnx.helper.make_node(
                "MatMul", [mid_name, u_t_name], [final_name], name=f"{base_name}__lowrank_mm2"
            ),
        ]
        if bias_name is not None:
            new_nodes.append(
                onnx.helper.make_node(
                    "Add", [final_name, bias_name], [node.output[0]],
                    name=f"{base_name}__lowrank_bias",
                )
            )

        replacements[idx] = new_nodes
        removed_initializers.add(weight_name)
        new_initializers.append(numpy_helper.from_array(v_t, v_t_name))
        new_initializers.append(numpy_helper.from_array(u_t, u_t_name))
        reports.append({
            "name": weight_name, "shape": (out_dim, in_dim), "rank": rank,
            "params_before": params_before, "params_after": params_after, "skipped": False,
        })

    if not replacements:
        return model, reports

    _replace_nodes(graph, replacements)
    kept_initializers = [
        init for init in graph.initializer if init.name not in removed_initializers
    ]
    kept_initializers.extend(new_initializers)
    del graph.initializer[:]
    graph.initializer.extend(kept_initializers)
    return model, reports


# ---------------------------------------------------------------------- Tucker-2 / CP


def _conv_attrs(node: Any) -> dict[str, Any]:
    return {
        "strides": _attr(node, "strides", [1, 1]),
        "pads": _attr(node, "pads", [0, 0, 0, 0]),
        "dilations": _attr(node, "dilations", [1, 1]),
    }


def onnx_conv_decompose(model: Any, params: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    import onnx
    from onnx import numpy_helper

    kind = params.get("kind", "tucker2")
    rank_pct = float(params.get("rank", 30))

    graph = model.graph
    initializers = {init.name: init for init in graph.initializer}
    candidates = _single_consumer_weight_nodes(graph, ("Conv",))

    replacements: dict[int, list[Any]] = {}
    new_initializers: list[Any] = []
    removed_initializers: set[str] = set()
    reports: list[dict[str, Any]] = []

    for weight_name, idx in candidates.items():
        node = graph.node[idx]
        weight_array = numpy_helper.to_array(initializers[weight_name])
        if weight_array.ndim != 4 or not np.issubdtype(weight_array.dtype, np.floating):
            continue
        if _attr(node, "group", 1) != 1:
            continue  # grouped/depthwise source conv: not a plain candidate, leave alone

        out_ch, in_ch, kh, kw = weight_array.shape
        params_before = out_ch * in_ch * kh * kw
        attrs = _conv_attrs(node)
        strides, pads, dilations = attrs["strides"], attrs["pads"], attrs["dilations"]

        bias_name = node.input[2] if len(node.input) > 2 and node.input[2] else None
        base_name = node.name or weight_name

        if kind == "cp":
            rank = max(1, min(out_ch, in_ch, round(min(out_ch, in_ch) * rank_pct / 100)))
            params_after = rank * (out_ch + in_ch + kh + kw)
        else:
            rank_out = choose_channel_rank(out_ch, rank_pct)
            rank_in = choose_channel_rank(in_ch, rank_pct)
            params_after = rank_out * rank_in * kh * kw + out_ch * rank_out + in_ch * rank_in

        if params_after >= params_before:
            reports.append({
                "name": weight_name, "shape": (out_ch, in_ch, kh, kw),
                "rank": rank if kind == "cp" else f"{rank_out}x{rank_in}",
                "params_before": params_before, "params_after": params_before, "skipped": True,
            })
            continue

        last_output = node.output[0] if bias_name is None else f"{node.output[0]}__lowrank_premerge"

        if kind == "cp":
            weights, factor_out, factor_in, factor_kh, factor_kw = factorize_cp(
                weight_array, rank
            )
            # Fold the CP scale into factor_out so no separate scale tensor is needed.
            factor_out_scaled = (factor_out * weights[None, :]).astype(weight_array.dtype)

            w_in = factor_in.T.reshape(rank, in_ch, 1, 1).astype(weight_array.dtype)
            w_kh = factor_kh.T.reshape(rank, 1, kh, 1).astype(weight_array.dtype)
            w_kw = factor_kw.T.reshape(rank, 1, 1, kw).astype(weight_array.dtype)
            w_out = factor_out_scaled.reshape(out_ch, rank, 1, 1)

            n_in = f"{weight_name}__cp_in"
            n_kh = f"{weight_name}__cp_kh"
            n_kw = f"{weight_name}__cp_kw"
            n_out = f"{weight_name}__cp_out"
            x_in, x_kh, x_kw = f"{base_name}__cp_x1", f"{base_name}__cp_x2", f"{base_name}__cp_x3"

            new_nodes = [
                onnx.helper.make_node(
                    "Conv", [node.input[0], n_in], [x_in], name=f"{base_name}__cp_conv_in",
                    strides=[1, 1], pads=[0, 0, 0, 0], dilations=[1, 1], group=1,
                ),
                onnx.helper.make_node(
                    "Conv", [x_in, n_kh], [x_kh], name=f"{base_name}__cp_conv_kh",
                    strides=[strides[0], 1], pads=[pads[0], 0, pads[2], 0],
                    dilations=[dilations[0], 1], group=rank,
                ),
                onnx.helper.make_node(
                    "Conv", [x_kh, n_kw], [x_kw], name=f"{base_name}__cp_conv_kw",
                    strides=[1, strides[1]], pads=[0, pads[1], 0, pads[3]],
                    dilations=[1, dilations[1]], group=rank,
                ),
                onnx.helper.make_node(
                    "Conv", [x_kw, n_out], [last_output], name=f"{base_name}__cp_conv_out",
                    strides=[1, 1], pads=[0, 0, 0, 0], dilations=[1, 1], group=1,
                ),
            ]
            new_initializers.extend([
                numpy_helper.from_array(w_in, n_in), numpy_helper.from_array(w_kh, n_kh),
                numpy_helper.from_array(w_kw, n_kw), numpy_helper.from_array(w_out, n_out),
            ])
            rank_report: Any = rank
        else:
            core, factor_out, factor_in = factorize_tucker2(weight_array, rank_out, rank_in)
            w_in = factor_in.reshape(in_ch, rank_in).T.reshape(rank_in, in_ch, 1, 1)
            w_core = core.astype(weight_array.dtype)
            w_out = factor_out.reshape(out_ch, rank_out, 1, 1)

            n_in = f"{weight_name}__tucker_in"
            n_core = f"{weight_name}__tucker_core"
            n_out = f"{weight_name}__tucker_out"
            x_in, x_core = f"{base_name}__tucker_x1", f"{base_name}__tucker_x2"

            new_nodes = [
                onnx.helper.make_node(
                    "Conv", [node.input[0], n_in], [x_in], name=f"{base_name}__tucker_conv_in",
                    strides=[1, 1], pads=[0, 0, 0, 0], dilations=[1, 1], group=1,
                ),
                onnx.helper.make_node(
                    "Conv", [x_in, n_core], [x_core], name=f"{base_name}__tucker_conv_core",
                    strides=strides, pads=pads, dilations=dilations, group=1,
                ),
                onnx.helper.make_node(
                    "Conv", [x_core, n_out], [last_output], name=f"{base_name}__tucker_conv_out",
                    strides=[1, 1], pads=[0, 0, 0, 0], dilations=[1, 1], group=1,
                ),
            ]
            new_initializers.extend([
                numpy_helper.from_array(w_in.astype(weight_array.dtype), n_in),
                numpy_helper.from_array(w_core, n_core),
                numpy_helper.from_array(w_out.astype(weight_array.dtype), n_out),
            ])
            rank_report = f"{rank_out}x{rank_in}"

        if bias_name is not None:
            new_nodes.append(
                onnx.helper.make_node(
                    "Add", [last_output, bias_name], [node.output[0]],
                    name=f"{base_name}__lowrank_bias",
                )
            )

        replacements[idx] = new_nodes
        removed_initializers.add(weight_name)
        reports.append({
            "name": weight_name, "shape": (out_ch, in_ch, kh, kw), "rank": rank_report,
            "params_before": params_before, "params_after": params_after, "skipped": False,
        })

    if not replacements:
        return model, reports

    _replace_nodes(graph, replacements)
    kept_initializers = [
        init for init in graph.initializer if init.name not in removed_initializers
    ]
    kept_initializers.extend(new_initializers)
    del graph.initializer[:]
    graph.initializer.extend(kept_initializers)
    return model, reports


__all__ = ["onnx_conv_decompose", "onnx_svd_decompose"]
