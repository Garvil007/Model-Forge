"""Smoke tests for catalog.json / per-operation JSON Schema export."""

from __future__ import annotations

import json
from pathlib import Path

from modelforge_catalog import CONVERTS, METHODS
from modelforge_catalog.export import (
    build_catalog,
    build_catalog_schema,
    build_param_schema,
    write_catalog,
)


def test_catalog_operation_count_matches_methods_and_converts() -> None:
    catalog = build_catalog()
    assert len(catalog["operations"]) == len(METHODS) + len(CONVERTS)


def test_catalog_schema_round_trips_and_covers_every_field_catalog_emits() -> None:
    schema = build_catalog_schema()
    reloaded = json.loads(json.dumps(schema))
    operation_props = set(reloaded["$defs"]["Operation"]["properties"])
    catalog = build_catalog()
    for op in catalog["operations"]:
        assert set(op).issubset(operation_props)


def test_every_operation_schema_is_valid_json_with_properties() -> None:
    for op in (*METHODS, *CONVERTS):
        schema = build_param_schema(op)
        dumped = json.dumps(schema)
        reloaded = json.loads(dumped)
        assert "properties" in reloaded


def test_write_catalog_writes_catalog_json_and_schemas(tmp_path: Path) -> None:
    write_catalog(tmp_path)
    assert (tmp_path / "catalog.json").exists()
    assert (tmp_path / "catalog.schema.json").exists()
    for op in (*METHODS, *CONVERTS):
        assert (tmp_path / "schemas" / f"{op.id}.schema.json").exists()
