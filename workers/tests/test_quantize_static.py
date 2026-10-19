"""ops.quantize_static: real calibrated INT8 static quantization of a tiny ONNX model (and,
if torch is installed in this dev environment, the TorchScript-source auto-export-to-ONNX
path), run end-to-end against the same fake-S3/fake-repository harness `test_quantize_dynamic.py`
uses."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnx.helper as helper
import pytest
from modelforge_db.records import DatasetRecord, JobEventRecord, ModelRecord

from ops import quantize_static

_MATRIX_SIZE = 8


def _tiny_onnx_bytes() -> bytes:
    rng = np.random.default_rng(0)
    x = helper.make_tensor_value_info("X", onnx.TensorProto.FLOAT, [1, _MATRIX_SIZE])
    y = helper.make_tensor_value_info("Y", onnx.TensorProto.FLOAT, [1, _MATRIX_SIZE])
    weight = helper.make_tensor(
        "W",
        onnx.TensorProto.FLOAT,
        [_MATRIX_SIZE, _MATRIX_SIZE],
        rng.standard_normal([_MATRIX_SIZE, _MATRIX_SIZE]).astype(np.float32).flatten().tolist(),
    )
    node = helper.make_node("MatMul", ["X", "W"], ["Y"])
    graph = helper.make_graph([node], "g", [x], [y], initializer=[weight])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


def _calibration_npy_bytes(num_samples: int = 40) -> bytes:
    rng = np.random.default_rng(1)
    array = rng.standard_normal((num_samples, _MATRIX_SIZE)).astype(np.float32)
    buffer = BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


class _FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects
        self.uploaded: dict[tuple[str, str], bytes] = {}

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        with open(local_path, "wb") as fh:
            fh.write(self.objects[(bucket, key)])

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        with open(local_path, "rb") as fh:
            self.uploaded[(bucket, key)] = fh.read()


class _FakeModelRepository:
    def __init__(self, record: ModelRecord) -> None:
        self.record = record

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        return self.record


class _FakeDatasetRepository:
    def __init__(self, record: DatasetRecord) -> None:
        self.record = record

    def get(self, user_id: str, dataset_id: str) -> DatasetRecord:
        return self.record


class _FakeJobRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_progress(self, user_id: str, job_id: str, *, status: str, progress_percent: int,
                         result: dict[str, Any] | None = None, error: dict[str, Any] | None = None,
                         timings: dict[str, Any] | None = None) -> None:
        self.calls.append({"status": status, "progress_percent": progress_percent,
                            "result": result, "error": error})


class _FakeJobEventRepository:
    def __init__(self) -> None:
        self.events: list[JobEventRecord] = []

    def append(self, user_id: str, job_id: str, *, stage: str, message: str,
               percent: int | None = None) -> JobEventRecord:
        event = JobEventRecord(user_id=user_id, job_id=job_id, stage=stage, message=message,
                                percent=percent, timestamp_ms=0, ttl=0)
        self.events.append(event)
        return event


class _AlwaysOkControl:
    def check(self) -> None:
        pass


def _model_record(
    *, filename: str = "tiny.onnx", model_format: str = "onnx", size_bytes: int = 0,
    param_count: int | None = None, details: dict[str, Any] | None = None,
) -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    return ModelRecord(
        user_id="user-1", model_id="model-1", filename=filename,
        s3_key=f"users/user-1/models/model-1{Path(filename).suffix}",
        size_bytes=size_bytes, format=model_format, family="generic", bits=32.0,
        param_count=param_count, details=details or {}, status="ready", created_at=now,
        updated_at=now, ttl=0,
    )


def _dataset_record(filename: str = "calib.npy") -> DatasetRecord:
    now = datetime.now(UTC).isoformat()
    return DatasetRecord(
        user_id="user-1", dataset_id="dataset-1", kind="calibration", filename=filename,
        s3_key="users/user-1/datasets/dataset-1.npy", size_bytes=10, model_id="model-1",
        created_at=now, ttl=0,
    )


def _run_op(
    model: ModelRecord, model_bytes: bytes, calib_bytes: bytes, *,
    params: dict[str, Any] | None = None, control: Any = None,
) -> tuple[_FakeJobRepository, _FakeJobEventRepository, _FakeS3]:
    dataset = _dataset_record()
    s3 = _FakeS3({
        ("mf-uploads", model.s3_key): model_bytes,
        ("mf-datasets", dataset.s3_key): calib_bytes,
    })
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()
    models = _FakeModelRepository(model)
    datasets = _FakeDatasetRepository(dataset)
    quantize_static.run(
        user_id="user-1", job_id="job-1", model_id="model-1",
        params={"calib": "dataset-1", "samples": 40, "per_channel": True, "method": "minmax",
                **(params or {})},
        operation=None, control=control or _AlwaysOkControl(), event_repo=events,
        job_repo=jobs, models_repo=models, datasets_repo=datasets, s3_client=s3,
    )
    return jobs, events, s3


def test_onnx_static_quantization_succeeds_and_uploads_quantized_model() -> None:
    model_bytes = _tiny_onnx_bytes()
    calib_bytes = _calibration_npy_bytes()
    model = _model_record(size_bytes=len(model_bytes), param_count=_MATRIX_SIZE * _MATRIX_SIZE)

    jobs, events, s3 = _run_op(model, model_bytes, calib_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["downloadName"] == "tiny.int8static.onnx"
    assert result["measuredOnValidation"] is False
    assert result["evaluation"] is None
    assert "Output similarity" in result["metrics"]

    uploaded_bytes = s3.uploaded[("mf-results", result["s3Key"])]
    assert len(uploaded_bytes) == result["outputBytes"]
    reloaded = onnx.load_from_string(uploaded_bytes)
    onnx.checker.check_model(reloaded)
    op_types = {node.op_type for node in reloaded.graph.node}
    assert "QuantizeLinear" in op_types
    assert "DequantizeLinear" in op_types

    stages = [event.stage for event in events.events]
    assert stages == [
        "Loading model", "Running calibration data", "Quantizing weights", "Measuring accuracy",
    ]


def test_missing_calibration_dataset_param_fails_cleanly() -> None:
    model_bytes = _tiny_onnx_bytes()
    model = _model_record(size_bytes=len(model_bytes))

    jobs, _events, _s3 = _run_op(model, model_bytes, b"", params={"calib": None})

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "invalid_calibration_data"


def test_corrupt_model_fails_cleanly_not_a_crash() -> None:
    model = _model_record()
    calib_bytes = _calibration_npy_bytes()
    dataset = _dataset_record()
    s3 = _FakeS3({
        ("mf-uploads", model.s3_key): b"not an onnx file",
        ("mf-datasets", dataset.s3_key): calib_bytes,
    })
    jobs = _FakeJobRepository()
    events = _FakeJobEventRepository()

    quantize_static.run(
        user_id="user-1", job_id="job-1", model_id="model-1",
        params={"calib": "dataset-1", "samples": 40}, operation=None,
        control=_AlwaysOkControl(), event_repo=events, job_repo=jobs,
        models_repo=_FakeModelRepository(model), datasets_repo=_FakeDatasetRepository(dataset),
        s3_client=s3,
    )

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] in ("unknown", "unsupported_operator")


def test_torch_statedict_is_refused_no_architecture_to_export() -> None:
    torch = pytest.importorskip("torch")
    state = {"lin.weight": torch.randn(_MATRIX_SIZE, _MATRIX_SIZE)}
    buffer = BytesIO()
    torch.save(state, buffer)
    model_bytes = buffer.getvalue()
    calib_bytes = _calibration_npy_bytes()
    model = _model_record(filename="tiny.pt", model_format="torch", size_bytes=len(model_bytes))

    jobs, _events, _s3 = _run_op(model, model_bytes, calib_bytes)

    assert jobs.calls[-1]["status"] == "failed"
    assert jobs.calls[-1]["error"]["code"] == "unsupported_operator"


def test_torchscript_source_is_exported_to_onnx_then_quantized(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")

    class _TinyLinear(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lin = torch.nn.Linear(_MATRIX_SIZE, _MATRIX_SIZE)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.lin(x)

    module = torch.jit.trace(_TinyLinear(), torch.randn(1, _MATRIX_SIZE))
    path = tmp_path / "scripted.pt"
    torch.jit.save(module, str(path))
    model_bytes = path.read_bytes()
    calib_bytes = _calibration_npy_bytes()
    model = _model_record(
        filename="tiny.pt", model_format="torchscript", size_bytes=len(model_bytes),
        param_count=_MATRIX_SIZE * _MATRIX_SIZE + _MATRIX_SIZE,
    )

    jobs, events, s3 = _run_op(model, model_bytes, calib_bytes)

    assert jobs.calls[-1]["status"] == "succeeded"
    result = jobs.calls[-1]["result"]
    assert result["downloadName"] == "tiny.int8static.onnx"

    uploaded_bytes = s3.uploaded[("mf-results", result["s3Key"])]
    reloaded = onnx.load_from_string(uploaded_bytes)
    onnx.checker.check_model(reloaded)
