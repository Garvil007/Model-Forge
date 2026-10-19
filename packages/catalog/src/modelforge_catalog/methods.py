"""Compression methods (the METHODS array in the prototype), one OperationSpec each.

Size/impact formulas are direct ports of the prototype's `size`/`impact` closures:
`size` estimates output bytes from a ModelInfo and the chosen param values; `impact`
estimates the relative accuracy/perplexity change those params will cause.
"""

from __future__ import annotations

from typing import Any

from .formats import GGUF_TYPES, SHARE_OF_LINEAR, gguf_type
from .models import OperationSpec, ParamOption, ParamSpec, ShowIf

_FINETUNE_HELP = (
    "Images folder (zip), CSV, JSONL or Parquet. A few thousand samples is often enough "
    "for fine-tuning."
)


def _train_data_param(show_if: ShowIf | None = None, required: bool = False) -> ParamSpec:
    return ParamSpec(
        name="train_data",
        label="Training data",
        type="file",
        accept=".zip,.tar,.csv,.jsonl,.parquet",
        help=_FINETUNE_HELP,
        show_if=show_if,
        required=required,
    )


def _finetune_params(default: bool) -> list[ParamSpec]:
    return [
        ParamSpec(
            name="finetune",
            label="Fine-tune afterwards to recover accuracy",
            type="check",
            default=default,
        ),
        _train_data_param(show_if=ShowIf("finetune", True)),
        ParamSpec(
            name="epochs",
            label="Fine-tuning epochs",
            type="number",
            default=3,
            min=1,
            max=100,
            show_if=ShowIf("finetune", True),
        ),
    ]


def _svd_k(v: dict[str, Any]) -> float:
    if v["mode"] == "energy":
        return 0.1 + (v["energy"] - 80) / 19 * 0.4
    return v["rank"] / 100


METHODS: tuple[OperationSpec, ...] = (
    # ---------------- Quantization ----------------
    OperationSpec(
        id="q_fp16",
        technique="quantization",
        label="FP16 (half precision)",
        description="Stores weights as 16-bit floats. The safest first step for any model.",
        accuracy="near-lossless",
        typical_impact="under 0.1% accuracy change",
        time_estimate="seconds",
        source_formats=("onnx", "torch", "torchscript", "keras", "safetensors", "yolo"),
        required_bit_width=32,
        size_estimate=lambda m, v: m.size * 16 / m.bits,
        impact_estimate=lambda m, v: 0.05,
        worker_image="cpu-torch",
    ),
    OperationSpec(
        id="q_bf16",
        technique="quantization",
        label="BF16 (brain float)",
        description=(
            "16-bit with FP32's range. The standard format for training and serving LLMs."
        ),
        accuracy="near-lossless",
        typical_impact="under 0.1% accuracy change",
        time_estimate="seconds",
        source_formats=("torch", "safetensors"),
        required_bit_width=32,
        size_estimate=lambda m, v: m.size * 16 / m.bits,
        impact_estimate=lambda m, v: 0.08,
        worker_image="cpu-torch",
    ),
    OperationSpec(
        id="q_int8_dyn",
        technique="quantization",
        label="INT8 dynamic",
        description=(
            "8-bit weights, activations quantized on the fly. No data needed. Works best on "
            "transformers and RNNs."
        ),
        accuracy="lossy",
        typical_impact="0.5 to 2% on CNNs, less on transformers",
        time_estimate="under a minute",
        source_formats=("onnx", "torch", "torchscript", "keras"),
        size_estimate=lambda m, v: m.size * 8.2 / m.bits,
        impact_estimate=lambda m, v: 1.1 if m.family == "vision" else 0.5,
        worker_image="cpu-torch",
    ),
    OperationSpec(
        id="q_int8_static",
        technique="quantization",
        label="INT8 static (calibrated)",
        description=(
            "Weights and activations in 8-bit, using sample inputs to pick the ranges. "
            "Fastest option on CPUs, phones and NPUs."
        ),
        accuracy="lossy",
        typical_impact="usually under 1% with good calibration data",
        time_estimate="1 to 10 minutes",
        source_formats=("onnx", "torch", "torchscript", "keras", "yolo"),
        worker_image="cpu-torch",
        params=(
            ParamSpec(
                name="calib",
                label="Calibration inputs",
                type="dataset",
                accept=".zip,.npz,.npy",
                required=True,
                help=(
                    "The id of an uploaded dataset with 100 to 1,000 real inputs, e.g. a zip "
                    "of images. No labels needed."
                ),
            ),
            ParamSpec(
                name="samples",
                label="Samples to use",
                type="range",
                min=50,
                max=1000,
                step=50,
                default=300,
            ),
            ParamSpec(
                name="per_channel",
                label="Per-channel weight scales (more accurate)",
                type="check",
                default=True,
            ),
            ParamSpec(
                name="method",
                label="Range estimation",
                type="select",
                default="minmax",
                options=(
                    ParamOption("minmax", "Min/max"),
                    ParamOption("entropy", "Entropy (KL divergence)"),
                    ParamOption("percentile", "Percentile 99.99%"),
                ),
            ),
        ),
        size_estimate=lambda m, v: m.size * 8.1 / m.bits,
        impact_estimate=lambda m, v: 0.4 if v["per_channel"] else 0.9,
    ),
    OperationSpec(
        id="q_gguf",
        technique="quantization",
        label="GGUF (llama.cpp)",
        description=(
            "Block-wise quantization for llama.cpp, Ollama and LM Studio. Runs LLMs on "
            "laptops and CPUs."
        ),
        accuracy="lossy",
        typical_impact="depends on the type below",
        time_estimate="2 to 10 minutes",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        params=(
            ParamSpec(
                name="qtype",
                label="Quantization type",
                type="select",
                default="Q4_K_M",
                options=tuple(ParamOption(t.value, t.label) for t in GGUF_TYPES),
            ),
            ParamSpec(
                name="imatrix",
                label="Use an importance matrix (better quality below 5 bits)",
                type="check",
                default=True,
            ),
            ParamSpec(
                name="imatrix_text",
                label="Calibration text",
                type="file",
                accept=".txt,.jsonl",
                help="Optional. Uses a general English sample if left empty.",
                show_if=ShowIf("imatrix", True),
            ),
        ),
        size_estimate=lambda m, v: m.params * gguf_type(v["qtype"]).bits_per_weight / 8,
        impact_estimate=lambda m, v: gguf_type(v["qtype"]).perplexity_delta
        * (0.75 if v["imatrix"] else 1),
        worker_image="gpu-base",
    ),
    OperationSpec(
        id="q_gptq",
        technique="quantization",
        label="GPTQ",
        description=(
            "Quantizes weights layer by layer while correcting the error it introduces. For "
            "GPU serving with vLLM, TGI or Transformers."
        ),
        accuracy="lossy",
        typical_impact="about 2 to 4% perplexity increase at 4-bit",
        time_estimate="10 to 60 minutes on a GPU",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        params=(
            ParamSpec(
                name="bits",
                label="Bits",
                type="select",
                default="4",
                options=(
                    ParamOption("8", "8-bit"),
                    ParamOption("4", "4-bit"),
                    ParamOption("3", "3-bit"),
                ),
            ),
            ParamSpec(
                name="group",
                label="Group size",
                type="select",
                default="128",
                options=(
                    ParamOption("32", "32 (more accurate, larger)"),
                    ParamOption("64", "64"),
                    ParamOption("128", "128 (standard)"),
                ),
            ),
            ParamSpec(
                name="dataset",
                label="Calibration dataset",
                type="select",
                default="wikitext2",
                options=(
                    ParamOption("wikitext2", "WikiText-2"),
                    ParamOption("c4", "C4"),
                    ParamOption("custom", "Upload my own"),
                ),
            ),
            ParamSpec(
                name="calib",
                label="Your calibration text",
                type="file",
                accept=".txt,.jsonl",
                show_if=ShowIf("dataset", "custom"),
            ),
            ParamSpec(
                name="act_order",
                label="Activation ordering (desc_act)",
                type="check",
                default=True,
            ),
        ),
        size_estimate=lambda m, v: m.params * (int(v["bits"]) + 32 / int(v["group"])) / 8,
        impact_estimate=lambda m, v: (
            {"8": 0.2, "4": 3, "3": 11}[v["bits"]]
            * (0.85 if v["act_order"] else 1)
            * (0.8 if v["group"] == "32" else 1)
        ),
        worker_image="gpu-base",
        queue="gpu",
    ),
    OperationSpec(
        id="q_awq",
        technique="quantization",
        label="AWQ (activation-aware)",
        description=(
            "Protects the small share of weights that matter most, based on activations. "
            "Often a little more accurate than GPTQ at 4-bit."
        ),
        accuracy="lossy",
        typical_impact="about 2 to 3% perplexity increase",
        time_estimate="10 to 30 minutes on a GPU",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        params=(
            ParamSpec(
                name="group",
                label="Group size",
                type="select",
                default="128",
                options=(ParamOption("64", "64"), ParamOption("128", "128 (standard)")),
            ),
            ParamSpec(
                name="kernel",
                label="Kernel format",
                type="select",
                default="gemm",
                options=(
                    ParamOption("gemm", "GEMM (best for batches)"),
                    ParamOption("gemv", "GEMV (best for single requests)"),
                ),
            ),
        ),
        size_estimate=lambda m, v: m.params * (4 + 32 / int(v["group"])) / 8,
        impact_estimate=lambda m, v: 2.2 if v["group"] == "64" else 2.6,
        worker_image="gpu-base",
        queue="gpu",
    ),
    OperationSpec(
        id="q_nf4",
        technique="quantization",
        label="bitsandbytes NF4",
        description=(
            "4-bit NormalFloat, loaded directly with Transformers. The format used for QLoRA "
            "fine-tuning."
        ),
        accuracy="lossy",
        typical_impact="about 3 to 4% perplexity increase",
        time_estimate="under a minute",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        params=(
            ParamSpec(
                name="double",
                label="Double quantization (saves ~0.4 bits per weight)",
                type="check",
                default=True,
            ),
            ParamSpec(
                name="compute",
                label="Compute dtype",
                type="select",
                default="bf16",
                options=(ParamOption("bf16", "BF16"), ParamOption("fp16", "FP16")),
            ),
        ),
        size_estimate=lambda m, v: m.params * (4.13 if v["double"] else 4.5) / 8,
        impact_estimate=lambda m, v: 3.4,
    ),
    # ---------------- Pruning ----------------
    OperationSpec(
        id="p_magnitude",
        technique="pruning",
        label="Magnitude pruning (unstructured)",
        description=(
            "Zeroes out the smallest weights anywhere in the network. Shrinks the file when "
            "stored sparse; speedups need a sparse-aware runtime."
        ),
        accuracy="lossy",
        typical_impact="little loss up to ~50% with fine-tuning, drops fast past 80%",
        time_estimate="minutes, or hours with fine-tuning",
        source_formats=("torch", "keras", "safetensors", "onnx"),
        params=(
            ParamSpec(
                name="sparsity", label="Sparsity", type="range", min=10, max=95, step=5,
                default=50, unit="%",
            ),
            ParamSpec(
                name="scope", label="Scope", type="select", default="global",
                options=(
                    ParamOption("global", "Global (best weights across all layers)"),
                    ParamOption("layer", "Same % in every layer"),
                ),
            ),
            ParamSpec(
                name="storage", label="Save as", type="select", default="sparse",
                options=(
                    ParamOption("sparse", "Sparse tensors (smaller file)"),
                    ParamOption("dense", "Dense with zeros (same size, zips well)"),
                ),
            ),
            *_finetune_params(True),
        ),
        size_estimate=lambda m, v: (
            m.size if v["storage"] == "dense" else m.size * min(1, (1 - v["sparsity"] / 100) * 1.3)
        ),
        impact_estimate=lambda m, v: (
            (lambda s: (s * 2 if s < 0.5 else 1 + ((s - 0.5) * 4) ** 2.2))(v["sparsity"] / 100)
            * (0.35 if v["finetune"] else 1)
            * (0.85 if v["scope"] == "global" else 1)
        ),
    ),
    OperationSpec(
        id="p_structured",
        technique="pruning",
        label="Structured pruning (channels / filters)",
        description=(
            "Removes whole channels, filters or attention heads, so the network becomes "
            "narrower. Faster on every device, no special runtime."
        ),
        accuracy="lossy",
        typical_impact="1 to 3% at 30% with fine-tuning",
        time_estimate="hours with fine-tuning",
        source_formats=("torch", "keras", "yolo", "safetensors"),
        params=(
            ParamSpec(
                name="ratio", label="Channels to remove", type="range", min=10, max=70,
                step=5, default=30, unit="%",
            ),
            ParamSpec(
                name="criterion", label="Importance score", type="select", default="l1",
                options=(
                    ParamOption("l1", "L1 norm"),
                    ParamOption("l2", "L2 norm"),
                    ParamOption("taylor", "Taylor expansion (uses data)"),
                ),
            ),
            *_finetune_params(True),
        ),
        size_estimate=lambda m, v: m.size * (1 - v["ratio"] / 100) ** 1.8,
        impact_estimate=lambda m, v: (
            (v["ratio"] / 100)
            * (6 if v["finetune"] else 28)
            * (0.8 if v["criterion"] == "taylor" else 1)
        ),
    ),
    OperationSpec(
        id="p_24",
        technique="pruning",
        label="2:4 semi-structured sparsity",
        description=(
            "Exactly 2 of every 4 weights are zero. NVIDIA Ampere and newer GPUs run this "
            "pattern about 1.3 to 1.6 times faster."
        ),
        accuracy="lossy",
        typical_impact="1 to 2% with fine-tuning",
        time_estimate="minutes, or hours with fine-tuning",
        source_formats=("torch", "safetensors", "onnx"),
        params=tuple(_finetune_params(True)),
        size_estimate=lambda m, v: m.size * 0.56,
        impact_estimate=lambda m, v: 1.2 if v["finetune"] else 4,
    ),
    OperationSpec(
        id="p_wanda",
        technique="pruning",
        label="One-shot LLM pruning (Wanda / SparseGPT)",
        description=(
            "Prunes an LLM in one pass using a small calibration set. No retraining needed."
        ),
        accuracy="lossy",
        typical_impact="about 5 to 10% perplexity increase at 50%",
        time_estimate="10 to 40 minutes on a GPU",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        params=(
            ParamSpec(
                name="algo", label="Algorithm", type="select", default="wanda",
                options=(
                    ParamOption("wanda", "Wanda (fast)"),
                    ParamOption("sparsegpt", "SparseGPT (more accurate, slower)"),
                ),
            ),
            ParamSpec(
                name="pattern", label="Sparsity pattern", type="select", default="unstructured",
                options=(
                    ParamOption("unstructured", "Unstructured"),
                    ParamOption("2:4", "2:4 (GPU speedup)"),
                ),
            ),
            ParamSpec(
                name="sparsity", label="Sparsity", type="range", min=10, max=70, step=5,
                default=50, unit="%", show_if=ShowIf("pattern", "unstructured"),
            ),
        ),
        size_estimate=lambda m, v: (
            m.size * 0.56
            if v["pattern"] == "2:4"
            else m.size * min(1, (1 - v["sparsity"] / 100) * 1.3)
        ),
        impact_estimate=lambda m, v: (
            (14 if v["pattern"] == "2:4" else (v["sparsity"] / 50) ** 2.5 * 8)
            * (0.8 if v["algo"] == "sparsegpt" else 1)
        ),
        worker_image="gpu-base",
        queue="gpu",
    ),
    # ---------------- Distillation ----------------
    OperationSpec(
        id="d_logit",
        technique="distillation",
        label="Response-based distillation",
        description=(
            "A smaller student learns to match your model's output probabilities. Your model "
            "only needs to run, so any runnable format works as the teacher."
        ),
        accuracy="lossy",
        typical_impact="student usually within 1 to 3% of the teacher",
        time_estimate="hours to days on a GPU",
        source_formats=("onnx", "tflite", "keras", "torch", "torchscript", "yolo"),
        allowed_families=("vision", "other"),
        params=(
            ParamSpec(
                name="student", label="Student model", type="select", default="half_width",
                options=(
                    ParamOption("half_width", "Same design, half the width (~25% of parameters)"),
                    ParamOption("half_depth", "Same design, half the depth (~50%)"),
                    ParamOption("compact", "Compact preset (MobileNet / TinyBERT style, ~15%)"),
                    ParamOption("custom", "Upload my own student"),
                ),
            ),
            ParamSpec(
                name="student_file", label="Student architecture", type="file",
                accept=".py,.onnx,.keras,.pt", show_if=ShowIf("student", "custom"),
            ),
            _train_data_param(required=True),
            ParamSpec(name="epochs", label="Epochs", type="number", default=30, min=1, max=500),
            ParamSpec(
                name="temp", label="Temperature", type="range", min=1, max=10, step=0.5,
                default=4,
                help=(
                    "Higher values soften the teacher's outputs so the student learns more "
                    "from its near-misses."
                ),
            ),
            ParamSpec(
                name="alpha", label="Weight on teacher vs. true labels", type="range", min=0,
                max=1, step=0.05, default=0.7,
            ),
        ),
        size_estimate=lambda m, v: (
            None
            if v["student"] == "custom"
            else {"half_width": 0.25, "half_depth": 0.5, "compact": 0.15}[v["student"]]
            * m.size
            * (32 / m.bits)
        ),
        impact_estimate=lambda m, v: (
            {"half_width": 2, "half_depth": 1.5, "compact": 3.5, "custom": 2}[v["student"]]
            * (1.8 if v["epochs"] < 10 else 1)
        ),
        worker_image="gpu-base",
        queue="gpu",
    ),
    OperationSpec(
        id="d_feature",
        technique="distillation",
        label="Feature-based distillation",
        description=(
            "The student also copies the teacher's intermediate layers, not just the outputs. "
            "Usually a little more accurate; needs PyTorch or Keras for the teacher."
        ),
        accuracy="lossy",
        typical_impact="student usually within 1 to 2% of the teacher",
        time_estimate="hours to days on a GPU",
        source_formats=("torch", "torchscript", "keras", "yolo"),
        allowed_families=("vision", "other"),
        params=(
            ParamSpec(
                name="student", label="Student model", type="select", default="half_width",
                options=(
                    ParamOption("half_width", "Same design, half the width (~25%)"),
                    ParamOption("half_depth", "Same design, half the depth (~50%)"),
                    ParamOption("custom", "Upload my own student"),
                ),
            ),
            ParamSpec(
                name="student_file", label="Student architecture", type="file",
                accept=".py,.onnx,.keras,.pt", show_if=ShowIf("student", "custom"),
            ),
            ParamSpec(
                name="layers", label="Layers to match", type="select", default="stages",
                options=(
                    ParamOption("last", "Last block only"),
                    ParamOption("stages", "End of every stage"),
                    ParamOption("auto", "Pick automatically"),
                ),
            ),
            _train_data_param(required=True),
            ParamSpec(name="epochs", label="Epochs", type="number", default=30, min=1, max=500),
        ),
        size_estimate=lambda m, v: (
            None
            if v["student"] == "custom"
            else {"half_width": 0.25, "half_depth": 0.5}[v["student"]] * m.size * (32 / m.bits)
        ),
        impact_estimate=lambda m, v: (
            {"half_width": 1.5, "half_depth": 1.1, "custom": 1.5}[v["student"]]
        ),
        worker_image="gpu-base",
        queue="gpu",
    ),
    OperationSpec(
        id="d_llm",
        technique="distillation",
        label="LLM distillation",
        description=(
            "Trains a smaller language model on your model's responses and token probabilities."
        ),
        accuracy="lossy",
        typical_impact="keeps most task quality; general knowledge drops",
        time_estimate="days on multiple GPUs",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        params=(
            ParamSpec(
                name="student", label="Student model", type="select", default="layerdrop",
                options=(
                    ParamOption("layerdrop", "Drop half the layers, then distill (~50%)"),
                    ParamOption("small", "Smaller model from the same family (~40%)"),
                ),
            ),
            ParamSpec(
                name="data", label="Training text", type="select", default="synthetic",
                options=(
                    ParamOption("synthetic", "Generate from the teacher"),
                    ParamOption("upload", "Upload prompts or text"),
                ),
            ),
            ParamSpec(
                name="texts", label="Your prompts or text", type="file",
                accept=".jsonl,.txt,.parquet", show_if=ShowIf("data", "upload"),
            ),
            ParamSpec(
                name="tokens", label="Training tokens", type="select", default="1B",
                options=(
                    ParamOption("250M", "250 million"),
                    ParamOption("1B", "1 billion"),
                    ParamOption("5B", "5 billion"),
                ),
            ),
        ),
        size_estimate=lambda m, v: m.size * (0.5 if v["student"] == "layerdrop" else 0.4),
        impact_estimate=lambda m, v: {"250M": 14, "1B": 9, "5B": 6}[v["tokens"]],
        worker_image="gpu-base",
        queue="gpu",
    ),
    # ---------------- Low-rank ----------------
    OperationSpec(
        id="l_svd",
        technique="lowrank",
        label="Truncated SVD (linear layers)",
        description=(
            "Replaces each large weight matrix with two thin ones. Biggest effect on "
            "transformers and fully connected layers."
        ),
        accuracy="lossy",
        typical_impact="under 1% when keeping 95% of the energy",
        time_estimate="minutes, or hours with fine-tuning",
        source_formats=("torch", "keras", "safetensors", "onnx"),
        params=(
            ParamSpec(
                name="mode", label="Choose rank by", type="select", default="energy",
                options=(
                    ParamOption("energy", "Keep a share of the matrix energy"),
                    ParamOption("fraction", "Keep a fixed share of the rank"),
                ),
            ),
            ParamSpec(
                name="energy", label="Energy to keep", type="range", min=80, max=99, step=1,
                default=95, unit="%", show_if=ShowIf("mode", "energy"),
            ),
            ParamSpec(
                name="rank", label="Rank to keep", type="range", min=5, max=75, step=5,
                default=25, unit="%", show_if=ShowIf("mode", "fraction"),
            ),
            ParamSpec(
                name="layers", label="Apply to", type="select", default="mlp",
                options=(
                    ParamOption("mlp", "Feed-forward / dense layers"),
                    ParamOption("attn", "Dense and attention projections"),
                ),
            ),
            *_finetune_params(False),
        ),
        size_estimate=lambda m, v: (
            m.size
            * (
                1
                - SHARE_OF_LINEAR[m.family]
                * (1 if v["layers"] == "attn" else 0.67)
                * max(0, 1 - 2 * _svd_k(v))
            )
        ),
        impact_estimate=lambda m, v: (
            (0.5 - min(0.49, _svd_k(v))) ** 2
            * 30
            * (0.4 if v["finetune"] else 1)
            * (1.3 if v["layers"] == "attn" else 1)
        ),
    ),
    OperationSpec(
        id="l_tucker",
        technique="lowrank",
        label="Tucker / CP decomposition (conv layers)",
        description=(
            "Splits each convolution into a chain of cheaper ones. Speeds up CNNs on CPUs "
            "and mobile."
        ),
        accuracy="lossy",
        typical_impact="1 to 2% at 30% rank with fine-tuning",
        time_estimate="minutes, or hours with fine-tuning",
        source_formats=("torch", "keras"),
        allowed_families=("vision",),
        params=(
            ParamSpec(
                name="kind", label="Decomposition", type="select", default="tucker2",
                options=(
                    ParamOption("tucker2", "Tucker-2 (stable, recommended)"),
                    ParamOption("cp", "CP (smaller, harder to fine-tune)"),
                ),
            ),
            ParamSpec(
                name="rank", label="Rank to keep", type="range", min=10, max=75, step=5,
                default=30, unit="%",
            ),
            *_finetune_params(True),
        ),
        size_estimate=lambda m, v: (
            m.size
            * (1 - 0.85 * max(0, 1 - (1.1 if v["kind"] == "cp" else 1.6) * v["rank"] / 100))
        ),
        impact_estimate=lambda m, v: (
            (75 - v["rank"]) / 45
            * (1.8 if v["finetune"] else 9)
            * (1.5 if v["kind"] == "cp" else 1)
        ),
    ),
)
