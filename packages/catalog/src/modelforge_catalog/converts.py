"""Format conversion operations (the CONVERTS array in the prototype)."""

from __future__ import annotations

from .models import OperationSpec, ParamOption, ParamSpec, ShowIf

CONVERTS: tuple[OperationSpec, ...] = (
    OperationSpec(
        id="c_onnx",
        technique="convert",
        label="ONNX",
        description="Portable graph that runs on ONNX Runtime across CPUs, GPUs and the browser.",
        accuracy="lossless",
        typical_impact="no accuracy change",
        time_estimate="seconds to minutes",
        source_formats=("torch", "torchscript", "keras", "yolo", "safetensors"),
        target_format="onnx",
        params=(
            ParamSpec(
                name="opset", label="Opset version", type="select", default="17",
                options=tuple(ParamOption(o, o) for o in ("13", "15", "17", "18", "20")),
            ),
            ParamSpec(
                name="shape", label="Example input shape", type="text", default="1,3,224,224",
                only_for=("torch", "torchscript"), help="Comma-separated, including batch.",
            ),
            ParamSpec(name="dynamic", label="Dynamic batch size", type="check", default=True),
        ),
        size_estimate=lambda m, v: m.size * 1,
    ),
    OperationSpec(
        id="c_tflite",
        technique="convert",
        label="TensorFlow Lite",
        description="For Android, iOS and microcontrollers. Converted to NHWC layout.",
        accuracy="near-lossless",
        typical_impact="tiny numerical differences",
        time_estimate="1 to 5 minutes",
        source_formats=("keras", "onnx", "yolo", "torch"),
        target_format="tflite",
        params=(
            ParamSpec(
                name="precision", label="Precision", type="select", default="fp32",
                options=(ParamOption("fp32", "FP32"), ParamOption("fp16", "FP16")),
            ),
        ),
        size_estimate=lambda m, v: m.size * (16 / m.bits if v["precision"] == "fp16" else 1),
    ),
    OperationSpec(
        id="c_torchscript",
        technique="convert",
        label="TorchScript",
        description="PyTorch model that loads without its Python source code.",
        accuracy="lossless",
        typical_impact="no accuracy change",
        time_estimate="seconds",
        source_formats=("onnx", "yolo", "torch"),
        target_format="torchscript",
        size_estimate=lambda m, v: m.size * 1,
    ),
    OperationSpec(
        id="c_savedmodel",
        technique="convert",
        label="TensorFlow SavedModel",
        description="For TF Serving and TensorFlow.js.",
        accuracy="lossless",
        typical_impact="no accuracy change",
        time_estimate="1 to 5 minutes",
        source_formats=("onnx", "keras"),
        target_format="savedmodel",
        size_estimate=lambda m, v: m.size * 1,
    ),
    OperationSpec(
        id="c_safetensors",
        technique="convert",
        label="safetensors",
        description="Safe, fast-loading weights format used by Hugging Face.",
        accuracy="lossless",
        typical_impact="no accuracy change",
        time_estimate="seconds",
        source_formats=("torch",),
        target_format="safetensors",
        size_estimate=lambda m, v: m.size * 1,
    ),
    OperationSpec(
        id="c_gguf",
        technique="convert",
        label="GGUF",
        description=(
            "For llama.cpp, Ollama and LM Studio. To also quantize, use GGUF under Compress."
        ),
        accuracy="near-lossless",
        typical_impact="tiny numerical differences",
        time_estimate="1 to 5 minutes",
        source_formats=("safetensors", "torch"),
        allowed_families=("llm",),
        target_format="gguf",
        params=(
            ParamSpec(
                name="outtype", label="Weight type", type="select", default="f16",
                options=(
                    ParamOption("f32", "F32"),
                    ParamOption("f16", "F16"),
                    ParamOption("bf16", "BF16"),
                    ParamOption("q8_0", "Q8_0"),
                ),
            ),
        ),
        size_estimate=lambda m, v: m.size
        * ({"f32": 32, "f16": 16, "bf16": 16, "q8_0": 8.5}[v["outtype"]] / m.bits),
    ),
    OperationSpec(
        id="c_openvino",
        technique="convert",
        label="OpenVINO IR",
        description="Optimized for Intel CPUs, GPUs and NPUs.",
        accuracy="near-lossless",
        typical_impact="tiny numerical differences",
        time_estimate="1 to 5 minutes",
        source_formats=("onnx", "torch", "keras", "yolo", "safetensors"),
        target_format="openvino",
        params=(
            ParamSpec(
                name="precision", label="Precision", type="select", default="fp16",
                options=(
                    ParamOption("fp32", "FP32"),
                    ParamOption("fp16", "FP16"),
                    ParamOption("int8", "INT8 weights"),
                ),
            ),
        ),
        size_estimate=lambda m, v: m.size
        * ({"fp32": 32, "fp16": 16, "int8": 8.2}[v["precision"]] / m.bits),
    ),
    OperationSpec(
        id="c_tensorrt",
        technique="convert",
        label="TensorRT engine",
        description=(
            "Fastest inference on NVIDIA GPUs. The engine only runs on the GPU model and "
            "TensorRT version it was built for."
        ),
        accuracy="near-lossless",
        typical_impact="tiny numerical differences",
        time_estimate="2 to 20 minutes",
        source_formats=("onnx", "yolo"),
        target_format="tensorrt",
        params=(
            ParamSpec(
                name="precision", label="Precision", type="select", default="fp16",
                options=(
                    ParamOption("fp32", "FP32"),
                    ParamOption("fp16", "FP16"),
                    ParamOption("int8", "INT8 (needs calibration inputs)"),
                ),
            ),
            ParamSpec(
                name="calib", label="Calibration inputs", type="file", accept=".zip,.npz",
                show_if=ShowIf("precision", "int8"),
            ),
            ParamSpec(
                name="gpu", label="Target GPU", type="select", default="l4",
                options=(
                    ParamOption("t4", "T4"),
                    ParamOption("l4", "L4"),
                    ParamOption("a100", "A100"),
                    ParamOption("h100", "H100"),
                    ParamOption("jetson", "Jetson Orin"),
                ),
            ),
        ),
        size_estimate=lambda m, v: m.size
        * ({"fp32": 32, "fp16": 16, "int8": 8.5}[v["precision"]] / m.bits),
        worker_image="gpu-base",
        queue="gpu",
    ),
    OperationSpec(
        id="c_coreml",
        technique="convert",
        label="Core ML",
        description="For iPhone, iPad and Mac, including the Apple Neural Engine.",
        accuracy="near-lossless",
        typical_impact="tiny numerical differences",
        time_estimate="1 to 5 minutes",
        source_formats=("torch", "torchscript", "keras", "yolo"),
        target_format="coreml",
        params=(
            ParamSpec(
                name="precision", label="Precision", type="select", default="fp16",
                options=(ParamOption("fp32", "FP32"), ParamOption("fp16", "FP16")),
            ),
        ),
        size_estimate=lambda m, v: m.size * ((16 if v["precision"] == "fp16" else 32) / m.bits),
    ),
)
