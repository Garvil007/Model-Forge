"""Content-based model format detection — never unpickles untrusted bytes.

Every detector here inspects magic bytes / binary headers / protobuf / HDF5 structure, not
the filename extension (the extension is only a tie-breaker when content is ambiguous, and a
mismatch is recorded rather than trusted). The torch detector in particular NEVER calls
`pickle.load`/`torch.load` on the pickle stream inside a torch zip checkpoint — it decodes
opcodes with `pickletools.genops` (which never imports or instantiates anything) and reads
tensor byte counts from the zip's own directory, never from executing the pickle graph.
"""

from __future__ import annotations

import json
import pickletools
import re
import struct
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from modelforge_catalog.formats import GGUF_TYPES

_MAX_SAFETENSORS_HEADER = 100 * 1024 * 1024
_MAX_GGUF_METADATA = 256 * 1024 * 1024
_MAX_FULL_FILE_BYTES = 512 * 1024 * 1024  # cap for formats that need the whole object
_MAX_GGUF_STRING = 1024 * 1024
_MAX_GGUF_ARRAY = 10_000_000
_MAX_GGUF_COUNT = 1_000_000


class DetectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DetectionResult:
    format: str
    family: str
    bits: float | None
    param_count: int | None
    inputs: str | None
    warnings: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


def _llm_or_vision(names: list[str]) -> str:
    joined = " ".join(names).lower()
    if any(k in joined for k in ("attn", "attention", "mlp", "embed_tokens", "wte", "wq", "wk")):
        return "llm"
    if any(k in joined for k in ("conv", "bn", "downsample", "stem", "stage")):
        return "vision"
    return "other"


# ---------------------------------------------------------------------------- GGUF
_GGUF_VALUE_READERS: dict[int, str] = {
    0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 10: "Q", 11: "q", 12: "d",
}

_GGML_TYPE_BITS: dict[int, float] = {
    0: 32.0, 1: 16.0, 2: 4.5, 3: 4.75, 6: 5.5, 7: 5.75, 8: 8.5, 9: 8.5,
    10: 3.4, 11: 3.9, 12: 4.8, 13: 5.7, 14: 6.6, 15: 8.5, 24: 8.0, 25: 16.0,
    26: 32.0, 27: 64.0, 28: 64.0, 29: 1.75, 30: 16.0,
}
_GGUF_BY_BITS: dict[float, str] = {t.bits_per_weight: t.value for t in GGUF_TYPES}


class _Cursor:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self._data):
            raise DetectionError("corrupt_file", "unexpected end of GGUF header")
        chunk = self._data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def string(self) -> str:
        length = self.u64()
        if length > _MAX_GGUF_STRING:
            raise DetectionError("corrupt_file", "GGUF string too long")
        return self.take(length).decode("utf-8", errors="replace")

    def value(self, value_type: int) -> Any:
        if value_type == 8:
            return self.string()
        if value_type == 9:
            elem_type = self.u32()
            count = self.u64()
            if count > _MAX_GGUF_ARRAY:
                raise DetectionError("corrupt_file", "GGUF array too long")
            return [self.value(elem_type) for _ in range(count)]
        fmt = _GGUF_VALUE_READERS.get(value_type)
        if fmt is None:
            raise DetectionError("corrupt_file", f"unknown GGUF value type {value_type}")
        size = struct.calcsize(fmt)
        return struct.unpack("<" + fmt, self.take(size))[0]


def detect_gguf(data: bytes) -> DetectionResult:
    cursor = _Cursor(data)
    if cursor.take(4) != b"GGUF":
        raise DetectionError("unrecognized_format", "missing GGUF magic")
    version = cursor.u32()
    if version not in (2, 3):
        raise DetectionError("unrecognized_format", f"unsupported GGUF version {version}")
    tensor_count = cursor.u64()
    kv_count = cursor.u64()
    if tensor_count > _MAX_GGUF_COUNT or kv_count > _MAX_GGUF_COUNT:
        raise DetectionError("corrupt_file", "GGUF tensor/kv count too large")

    metadata: dict[str, Any] = {}
    for _ in range(kv_count):
        key = cursor.string()
        value_type = cursor.u32()
        metadata[key] = cursor.value(value_type)
        if cursor.pos > _MAX_GGUF_METADATA:
            raise DetectionError("corrupt_file", "GGUF metadata exceeds size cap")

    total_params = 0
    type_counts: dict[int, int] = {}
    names: list[str] = []
    for _ in range(tensor_count):
        name = cursor.string()
        names.append(name)
        n_dims = cursor.u32()
        if n_dims > 8:
            raise DetectionError("corrupt_file", "GGUF tensor has too many dims")
        dims = [cursor.u64() for _ in range(n_dims)]
        ggml_type = cursor.u32()
        cursor.u64()  # offset, unused for detection
        numel = 1
        for d in dims:
            numel *= d
        total_params += numel
        type_counts[ggml_type] = type_counts.get(ggml_type, 0) + numel

    weighted_bits = 0.0
    for ggml_type, count in type_counts.items():
        weighted_bits += _GGML_TYPE_BITS.get(ggml_type, 8.0) * count
    bits = round(weighted_bits / total_params, 2) if total_params else None
    for catalog_bits in _GGUF_BY_BITS:
        if bits is not None and abs(bits - catalog_bits) < 0.05:
            bits = catalog_bits
            break

    architecture = metadata.get("general.architecture", "")
    family = "llm" if architecture or _llm_or_vision(names) == "llm" else _llm_or_vision(names)

    return DetectionResult(
        format="gguf",
        family=family,
        bits=bits,
        param_count=total_params or None,
        inputs=None,
        extras={"ggufArchitecture": architecture},
    )


# ------------------------------------------------------------------------ safetensors
_DTYPE_BITS: dict[str, float] = {
    "F64": 64, "I64": 64, "U64": 64, "F32": 32, "I32": 32, "U32": 32,
    "F16": 16, "BF16": 16, "I16": 16, "U16": 16, "I8": 8, "U8": 8, "BOOL": 1,
    "F8_E4M3": 8, "F8_E5M2": 8,
}


def detect_safetensors(data: bytes) -> DetectionResult:
    if len(data) < 8:
        raise DetectionError("corrupt_file", "file too small for a safetensors header")
    (header_len,) = struct.unpack("<Q", data[:8])
    if header_len < 2 or header_len > _MAX_SAFETENSORS_HEADER or 8 + header_len > len(data):
        raise DetectionError("corrupt_file", "invalid safetensors header length")
    try:
        header = json.loads(data[8 : 8 + header_len])
    except json.JSONDecodeError as error:
        raise DetectionError("corrupt_file", "invalid safetensors JSON header") from error

    total_params = 0
    weighted_bits = 0.0
    names: list[str] = []
    for name, info in header.items():
        if name == "__metadata__" or not isinstance(info, dict):
            continue
        names.append(name)
        shape = info.get("shape", [])
        numel = 1
        for d in shape:
            numel *= int(d)
        total_params += numel
        weighted_bits += _DTYPE_BITS.get(info.get("dtype", ""), 16) * numel

    bits = round(weighted_bits / total_params, 2) if total_params else None
    return DetectionResult(
        format="safetensors",
        family=_llm_or_vision(names),
        bits=bits,
        param_count=total_params or None,
        inputs=None,
    )


# -------------------------------------------------------------------------------- torch
_STORAGE_DTYPE_BITS: dict[str, float] = {
    "DoubleStorage": 64, "FloatStorage": 32, "HalfStorage": 16, "BFloat16Storage": 16,
    "LongStorage": 64, "IntStorage": 32, "ShortStorage": 16, "CharStorage": 8,
    "ByteStorage": 8, "BoolStorage": 1,
}
_GLOBAL_OPCODES = {"GLOBAL", "STACK_GLOBAL"}
_ALLOWED_GLOBAL_MODULES = (
    "torch", "collections", "builtins", "__builtin__", "numpy", "numpy.core.multiarray",
)


def detect_torch_zip(data: bytes) -> DetectionResult:
    """Torch's zip-based checkpoint format. Reads opcode-level structure of data.pkl with
    `pickletools.genops` (decode only — never instantiates or calls anything) purely to spot
    storage dtypes and any suspicious global reference; actual tensor byte counts come from
    the zip's own member sizes, never from executing the pickle."""
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise DetectionError("unrecognized_format", "not a zip-based torch checkpoint") from error

    pkl_names = [n for n in archive.namelist() if n.endswith("data.pkl")]
    if not pkl_names:
        raise DetectionError("unrecognized_format", "no data.pkl member in zip")
    pkl_bytes = archive.read(pkl_names[0])
    if len(pkl_bytes) > 64 * 1024 * 1024:
        raise DetectionError("corrupt_file", "data.pkl unexpectedly large")

    storage_dtypes: list[str] = []
    suspicious: list[str] = []
    opcount = 0
    for opcode, arg, _pos in pickletools.genops(pkl_bytes):
        opcount += 1
        if opcount > 5_000_000:
            raise DetectionError("corrupt_file", "pickle stream has too many opcodes")
        if opcode.name in _GLOBAL_OPCODES and isinstance(arg, str):
            module = arg.split()[0] if " " in arg else arg.split("\n")[0]
            name = arg.split()[-1] if " " in arg else ""
            if name in _STORAGE_DTYPE_BITS:
                storage_dtypes.append(name)
            elif not module.startswith(_ALLOWED_GLOBAL_MODULES):
                suspicious.append(arg)

    data_member_sizes = [
        info.file_size
        for info in archive.infolist()
        if "/data/" in info.filename or info.filename.rsplit("/", 1)[-1].isdigit()
    ]
    total_storage_bytes = sum(data_member_sizes)

    dominant_dtype = max(set(storage_dtypes), key=storage_dtypes.count) if storage_dtypes else None
    bits = _STORAGE_DTYPE_BITS.get(dominant_dtype, 32.0) if dominant_dtype else 32.0
    param_count = int(total_storage_bytes / (bits / 8)) if total_storage_bytes else None

    warnings = []
    extras: dict[str, Any] = {"paramsEstimated": True}
    if suspicious:
        extras["requiresCodeToLoad"] = True
        warnings.append("checkpoint references code outside torch/collections/numpy")
    if any("ultralytics" in g for g in suspicious):
        return DetectionResult(
            format="yolo", family="vision", bits=bits, param_count=param_count,
            inputs=None, warnings=warnings, extras=extras,
        )

    names = [n for n in archive.namelist()]
    return DetectionResult(
        format="torch", family=_llm_or_vision(names), bits=bits, param_count=param_count,
        inputs=None, warnings=warnings, extras=extras,
    )


def detect_legacy_pickle(data: bytes) -> DetectionResult:
    """Pre-zip torch format: a raw pickle stream. Same genops-only decode, no byte-count
    source available (no zip directory), so this always reports an estimate."""
    if len(data) < 2:
        raise DetectionError("unrecognized_format", "file too small")
    opcount = 0
    storage_dtypes: list[str] = []
    for opcode, arg, _pos in pickletools.genops(data[: 8 * 1024 * 1024]):
        opcount += 1
        if opcount > 2_000_000:
            break
        if opcode.name in _GLOBAL_OPCODES and isinstance(arg, str):
            name = arg.split()[-1] if " " in arg else ""
            if name in _STORAGE_DTYPE_BITS:
                storage_dtypes.append(name)
    dominant = max(set(storage_dtypes), key=storage_dtypes.count) if storage_dtypes else None
    bits = _STORAGE_DTYPE_BITS.get(dominant, 32.0) if dominant else 32.0
    return DetectionResult(
        format="torch", family="other", bits=bits, param_count=None,
        inputs=None, warnings=["legacy pickle format — size-based estimate only"],
        extras={"paramsEstimated": True},
    )


# --------------------------------------------------------------------------------- keras
def detect_hdf5(data: bytes) -> DetectionResult:
    import h5py

    with h5py.File(BytesIO(data), "r") as handle:
        model_config = handle.attrs.get("model_config")
        config = json.loads(model_config) if model_config else {}
        class_name = str(config.get("class_name", ""))

        total_params = 0
        weighted_bits = 0.0
        layer_names: list[str] = []

        def visit(name: str, obj: Any) -> None:
            nonlocal total_params, weighted_bits
            if hasattr(obj, "shape") and hasattr(obj, "dtype"):
                numel = 1
                for d in obj.shape:
                    numel *= int(d)
                total_params += numel
                weighted_bits += obj.dtype.itemsize * 8 * numel
            layer_names.append(name)

        handle.visititems(visit)
        bits = round(weighted_bits / total_params, 2) if total_params else 32.0
        family = "vision" if "conv" in class_name.lower() else _llm_or_vision(layer_names)
        return DetectionResult(
            format="keras", family=family, bits=bits, param_count=total_params or None,
            inputs=None,
        )


def detect_keras_archive(data: bytes) -> DetectionResult:
    """.keras files are a zip of config.json + model.weights.h5."""
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise DetectionError("unrecognized_format", "not a .keras zip archive") from error
    weights_names = [n for n in archive.namelist() if n.endswith("model.weights.h5")]
    if not weights_names:
        raise DetectionError("unrecognized_format", "no model.weights.h5 in .keras archive")
    return detect_hdf5(archive.read(weights_names[0]))


# ---------------------------------------------------------------------------------- onnx
def detect_onnx(data: bytes) -> DetectionResult:
    import onnx

    model = onnx.load_model_from_string(data)  # protobuf parse, not pickle — safe
    graph = model.graph
    initializer_names = {i.name for i in graph.initializer}

    total_params = 0
    weighted_bits = 0.0
    _ONNX_DTYPE_BITS = {1: 32, 10: 16, 11: 64, 6: 32, 7: 64, 2: 8, 3: 8}
    for initializer in graph.initializer:
        numel = 1
        for d in initializer.dims:
            numel *= int(d)
        total_params += numel
        weighted_bits += _ONNX_DTYPE_BITS.get(initializer.data_type, 32) * numel

    input_descs = []
    for inp in graph.input:
        if inp.name in initializer_names:
            continue
        dims = [
            str(d.dim_value) if d.dim_value else (d.dim_param or "?")
            for d in inp.type.tensor_type.shape.dim
        ]
        input_descs.append(f"{inp.name} [{', '.join(dims)}]")

    bits = round(weighted_bits / total_params, 2) if total_params else 32.0
    names = [i.name for i in graph.initializer]
    return DetectionResult(
        format="onnx", family=_llm_or_vision(names), bits=bits,
        param_count=total_params or None, inputs=", ".join(input_descs) or None,
    )


# ---------------------------------------------------------------------------------- tflite
def detect_tflite(data: bytes, size: int) -> DetectionResult:
    """Confirms the FlatBuffers TFLite magic; full schema parsing isn't implemented yet
    (see docs/PROGRESS.md follow-ups), so params/bits are a size-based estimate."""
    return DetectionResult(
        format="tflite", family="vision", bits=8.0, param_count=int(size / 1), inputs=None,
        warnings=["tflite detection confirms the file header only; params/bits are estimated"],
        extras={"paramsEstimated": True},
    )


_FAMILY_NAME_RE = re.compile(r"(resnet|vgg|yolo|efficientnet|mobilenet|bert|gpt|llama|t5)", re.I)


def sniff_and_detect(data: bytes, size: int, extension_hint: str | None) -> DetectionResult:
    """Dispatch purely on content. `extension_hint` is recorded if it disagrees, never trusted."""
    if data.startswith(b"GGUF"):
        result = detect_gguf(data)
    elif _looks_like_safetensors(data):
        result = detect_safetensors(data)
    elif data[:2] == b"PK":
        try:
            result = detect_torch_zip(data)
        except DetectionError:
            result = detect_keras_archive(data)
    elif data[:4] == b"\x89HDF":
        result = detect_hdf5(data)
    elif len(data) >= 8 and data[4:8] == b"TFL3":
        result = detect_tflite(data, size)
    elif _looks_like_onnx(data):
        result = detect_onnx(data)
    else:
        try:
            result = detect_legacy_pickle(data)
        except DetectionError as error:
            raise DetectionError("unrecognized_format", "could not identify file format") from error

    detected_ext_family = {"gguf": "gguf", "safetensors": "safetensors", "torch": "torch"}
    if extension_hint and detected_ext_family.get(result.format, result.format) != extension_hint:
        result.extras["extensionMismatch"] = {
            "declared": extension_hint, "detected": result.format
        }
    return result


def _looks_like_safetensors(data: bytes) -> bool:
    if len(data) < 10:
        return False
    (header_len,) = struct.unpack("<Q", data[:8])
    if header_len < 2 or 8 + header_len > len(data) + 1_000_000:
        return False
    return data[8:9] == b"{"


def _looks_like_onnx(data: bytes) -> bool:
    try:
        import onnx  # noqa: F401
    except ImportError:
        return False
    return len(data) > 0 and data[0] in (0x08, 0x0A, 0x12, 0x1A)
