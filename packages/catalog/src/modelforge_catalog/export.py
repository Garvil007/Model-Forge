"""Export the catalog as JSON for the frontend: catalog.json plus one JSON Schema per operation.

1. Callers: `python -m modelforge_catalog.export <out_dir>` (CLI); apps/web build step will
   eventually consume the generated catalog.json.
2. Searched src/modelforge_catalog — no existing export/serialization module.
3. Data schema: see module docstring and function bodies below (catalog.json shape, JSON Schema
   per operation).
4. User instruction (verbatim, from CLAUDE.md-driven task): "Export two artifacts: catalog.json
   for the frontend, and a JSON Schema per operation's params."
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .converts import CONVERTS
from .methods import METHODS
from .models import OperationSpec, ParamSpec, TechniqueInfo
from .techniques import TECHNIQUES

OPERATIONS: tuple[OperationSpec, ...] = METHODS + CONVERTS


def _technique_to_dict(t: TechniqueInfo) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "tag": t.tag,
        "mechanism": t.mechanism,
        "hardwareImpact": t.hardware_impact,
        "complexity": t.complexity,
        "bars": list(t.bars),
    }


def _param_to_dict(p: ParamSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"name": p.name, "label": p.label, "type": p.type}
    if p.default is not None:
        out["default"] = p.default
    if p.help is not None:
        out["help"] = p.help
    if p.required:
        out["required"] = True
    if p.options:
        out["options"] = [{"value": o.value, "label": o.label} for o in p.options]
    if p.min is not None:
        out["min"] = p.min
    if p.max is not None:
        out["max"] = p.max
    if p.step is not None:
        out["step"] = p.step
    if p.unit is not None:
        out["unit"] = p.unit
    if p.accept is not None:
        out["accept"] = p.accept
    if p.only_for:
        out["onlyFor"] = list(p.only_for)
    if p.show_if is not None:
        out["showIf"] = {"field": p.show_if.field, "equals": p.show_if.equals}
    return out


def _operation_to_dict(op: OperationSpec) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": op.id,
        "technique": op.technique,
        "label": op.label,
        "description": op.description,
        "accuracy": op.accuracy,
        "typicalImpact": op.typical_impact,
        "timeEstimate": op.time_estimate,
        "sourceFormats": list(op.source_formats),
        "workerImage": op.worker_image,
        "queue": op.queue,
    }
    if op.allowed_families:
        out["allowedFamilies"] = list(op.allowed_families)
    if op.required_bit_width is not None:
        out["requiredBitWidth"] = op.required_bit_width
    if op.target_format is not None:
        out["targetFormat"] = op.target_format
    if op.params:
        out["params"] = [_param_to_dict(p) for p in op.params]
    return out


def build_catalog() -> dict[str, Any]:
    """Build the catalog.json payload (no size/impact callables — those stay server-side)."""
    return {
        "techniques": [_technique_to_dict(t) for t in TECHNIQUES],
        "operations": [_operation_to_dict(op) for op in OPERATIONS],
    }


def _param_schema(p: ParamSpec) -> dict[str, Any]:
    if p.type == "select":
        return {"type": "string", "enum": [o.value for o in p.options]}
    if p.type == "range":
        schema: dict[str, Any] = {"type": "number"}
        if p.min is not None:
            schema["minimum"] = p.min
        if p.max is not None:
            schema["maximum"] = p.max
        if p.step is not None:
            schema["multipleOf"] = p.step
        return schema
    if p.type == "check":
        return {"type": "boolean"}
    if p.type == "number":
        schema = {"type": "number"}
        if p.min is not None:
            schema["minimum"] = p.min
        if p.max is not None:
            schema["maximum"] = p.max
        return schema
    if p.type == "text":
        return {"type": "string"}
    if p.type == "file":
        return {"type": "string", "description": "Uploaded object key or filename"}
    raise ValueError(f"Unknown param type: {p.type}")  # pragma: no cover - exhaustive above


def build_param_schema(op: OperationSpec) -> dict[str, Any]:
    """Build a JSON Schema (draft 2020-12) for one operation's params."""
    properties = {p.name: _param_schema(p) for p in op.params}
    required = [p.name for p in op.params if p.required]
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": op.label,
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def write_catalog(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalog.json").write_text(json.dumps(build_catalog(), indent=2), encoding="utf-8")
    schema_dir = out_dir / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for op in OPERATIONS:
        schema_path = schema_dir / f"{op.id}.schema.json"
        schema_path.write_text(json.dumps(build_param_schema(op), indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: python -m modelforge_catalog.export <out_dir>", file=sys.stderr)
        return 2
    write_catalog(Path(argv[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
