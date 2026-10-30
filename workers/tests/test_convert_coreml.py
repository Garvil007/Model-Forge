"""ops.convert_coreml: TorchScript/Keras (coremltools.convert) and YOLO (Ultralytics' own
coreml exporter) -> Core ML, using tiny real models built inside the test.

`coremltools` isn't installed in this sandbox (no macOS Core ML runtime to validate
against anyway — see the op's own docstring), so every test that needs it is skipped via
`pytest.importorskip`, same convention `test_convert_torchscript.py`'s YOLO test already
uses for `ultralytics`.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import pytest
import torch
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_coreml

_C_COREML = {op.id: op for op in CONVERTS}["c_coreml"]


class _TinyModule(torch.nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.relu(x)


def _tiny_torchscript_bytes() -> bytes:
    scripted = torch.jit.script(_TinyModule())
    buffer = io.BytesIO()
    torch.jit.save(scripted, buffer)
    return buffer.getvalue()


def test_torchscript_source_converts_to_coreml() -> None:
    pytest.importorskip("coremltools")
    model = model_record(filename="model.pt", model_format="torchscript")
    jobs, events, s3 = run_convert(
        convert_coreml, _C_COREML, model, _tiny_torchscript_bytes(), params={"shape": "1,4"}
    )
    assert jobs.calls[-1]["status"] == "succeeded"
    stages = {e.stage for e in events.events}
    assert stages == {"Loading model", "Converting to Core ML", "Checking outputs match"}

    key = next(iter(s3.uploaded))
    with zipfile.ZipFile(io.BytesIO(s3.uploaded[key])) as archive:
        assert any(name.startswith("model.mlpackage/") for name in archive.namelist())


def test_torch_statedict_source_is_refused_cleanly() -> None:
    model = model_record(filename="model.pt", model_format="torch")
    buffer = io.BytesIO()
    torch.save({"w": torch.randn(3, 4)}, buffer)
    jobs, _events, _s3 = run_convert(convert_coreml, _C_COREML, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_yolo_source_converts_to_coreml() -> None:
    pytest.importorskip("coremltools")
    pytest.importorskip("ultralytics")
    from ultralytics import YOLO

    with tempfile.TemporaryDirectory() as tmp:
        checkpoint = Path(tmp) / "tiny.pt"
        yolo = YOLO("yolo11n.yaml")
        yolo.save(str(checkpoint))
        model_bytes = checkpoint.read_bytes()

    model = model_record(filename="model.pt", model_format="yolo")
    jobs, _events, _s3 = run_convert(convert_coreml, _C_COREML, model, model_bytes)
    assert jobs.calls[-1]["status"] == "succeeded"
