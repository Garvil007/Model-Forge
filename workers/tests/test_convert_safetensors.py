"""ops.convert_safetensors: PyTorch state_dict -> safetensors, including the shared-storage
contiguous-tensor gotcha this op guards against (see its module docstring)."""

from __future__ import annotations

import io

import safetensors.torch
import torch
from _convert_fakes import model_record, run_convert
from modelforge_catalog.converts import CONVERTS

from ops import convert_safetensors

_C_SAFETENSORS = {op.id: op for op in CONVERTS}["c_safetensors"]


def test_torch_statedict_converts_to_safetensors() -> None:
    state = {"weight": torch.randn(3, 4), "bias": torch.randn(3)}
    buffer = io.BytesIO()
    torch.save(state, buffer)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _events, s3 = run_convert(convert_safetensors, _C_SAFETENSORS, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "succeeded"

    key = next(iter(s3.uploaded))
    reloaded = safetensors.torch.load(s3.uploaded[key])
    assert set(reloaded) == {"weight", "bias"}
    assert torch.equal(reloaded["weight"], state["weight"])
    assert torch.equal(reloaded["bias"], state["bias"])


def test_shared_storage_tensors_are_made_contiguous_before_saving() -> None:
    # A weight-tying-like scenario: two names pointing at views of the same storage, which
    # `safetensors.torch.save_file` refuses to serialize directly.
    base = torch.randn(4, 4)
    state = {"full": base, "view": base[:2]}
    buffer = io.BytesIO()
    torch.save(state, buffer)

    model = model_record(filename="model.pt", model_format="torch")
    jobs, _events, s3 = run_convert(convert_safetensors, _C_SAFETENSORS, model, buffer.getvalue())
    assert jobs.calls[-1]["status"] == "succeeded"

    key = next(iter(s3.uploaded))
    reloaded = safetensors.torch.load(s3.uploaded[key])
    assert torch.equal(reloaded["view"], base[:2])
