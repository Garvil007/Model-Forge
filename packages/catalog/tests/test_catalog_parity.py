"""Proves the Python catalog matches docs/ui-prototype.html exactly on ids, labels, defaults."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from modelforge_catalog import CONVERTS, METHODS, TECHNIQUES

TESTS_DIR = Path(__file__).parent


@pytest.fixture(scope="module")
def prototype() -> dict:
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH; cannot extract docs/ui-prototype.html for parity check")
    result = subprocess.run(
        ["node", "extract_prototype.js"],
        cwd=TESTS_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_techniques_match_prototype(prototype: dict) -> None:
    by_id = {t["id"]: t for t in prototype["techs"]}
    assert set(by_id) == {t.id for t in TECHNIQUES}
    for t in TECHNIQUES:
        proto = by_id[t.id]
        assert t.name == proto["name"]
        assert t.tag == proto["tag"]


def test_method_ids_match_prototype(prototype: dict) -> None:
    proto_ids = {m["id"] for m in prototype["methods"]}
    our_ids = {m.id for m in METHODS}
    assert our_ids == proto_ids


def test_method_labels_and_defaults_match_prototype(prototype: dict) -> None:
    by_id = {m["id"]: m for m in prototype["methods"]}
    for method in METHODS:
        proto = by_id[method.id]
        assert method.label == proto["label"], f"{method.id}: label mismatch"
        proto_params = {p["name"]: p for p in proto.get("params", [])}
        for param in method.params:
            if param.type == "file":
                continue
            proto_param = proto_params.get(param.name)
            assert proto_param is not None, f"{method.id}: missing param {param.name}"
            if "default" in proto_param:
                assert param.default == proto_param["default"], (
                    f"{method.id}.{param.name}: default mismatch "
                    f"({param.default!r} != {proto_param['default']!r})"
                )


def test_convert_ids_and_labels_match_prototype(prototype: dict) -> None:
    by_id = {c["id"]: c for c in prototype["converts"]}
    assert {c.id for c in CONVERTS} == set(by_id)
    for convert in CONVERTS:
        assert convert.label == by_id[convert.id]["label"]
