"""Shared fakes for `test_convert_*.py` — same shape as `test_fp_cast.py`'s and
`test_quantize_static.py`'s, factored out once six convert-op test files need it instead
of being copy-pasted into each.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modelforge_db.records import JobEventRecord, ModelRecord


class FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects
        self.uploaded: dict[tuple[str, str], bytes] = {}

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        with open(local_path, "wb") as fh:
            fh.write(self.objects[(bucket, key)])

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        with open(local_path, "rb") as fh:
            self.uploaded[(bucket, key)] = fh.read()


class FakeModelRepository:
    def __init__(self, record: ModelRecord) -> None:
        self.record = record

    def get(self, user_id: str, model_id: str) -> ModelRecord:
        return self.record


class FakeJobRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_progress(
        self, user_id: str, job_id: str, *, status: str, progress_percent: int,
        result: dict[str, Any] | None = None, error: dict[str, Any] | None = None,
        timings: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append({"status": status, "progress_percent": progress_percent,
                            "result": result, "error": error})


class FakeJobEventRepository:
    def __init__(self) -> None:
        self.events: list[JobEventRecord] = []

    def append(self, user_id: str, job_id: str, *, stage: str, message: str,
               percent: int | None = None) -> JobEventRecord:
        event = JobEventRecord(user_id=user_id, job_id=job_id, stage=stage, message=message,
                                percent=percent, timestamp_ms=0, ttl=0)
        self.events.append(event)
        return event


class AlwaysOkControl:
    def check(self) -> None:
        pass


def model_record(
    *, filename: str, model_format: str, bits: float = 32.0, size_bytes: int = 0,
    details: dict[str, Any] | None = None,
) -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    return ModelRecord(
        user_id="user-1", model_id="model-1", filename=filename,
        s3_key=f"users/user-1/models/model-1{Path(filename).suffix}",
        size_bytes=size_bytes, format=model_format, family="other", bits=bits,
        param_count=None, details=details or {}, status="ready", created_at=now,
        updated_at=now, ttl=0,
    )


def run_convert(
    op_module: Any, operation: Any, model: ModelRecord, model_bytes: bytes,
    params: dict[str, Any] | None = None, control: Any = None,
) -> tuple[FakeJobRepository, FakeJobEventRepository, FakeS3]:
    s3 = FakeS3({("mf-uploads", model.s3_key): model_bytes})
    jobs = FakeJobRepository()
    events = FakeJobEventRepository()
    models = FakeModelRepository(model)
    op_module.run(
        user_id="user-1", job_id="job-1", model_id="model-1", params=params or {},
        operation=operation, control=control or AlwaysOkControl(), event_repo=events,
        job_repo=jobs, models_repo=models, s3_client_override=s3,
    )
    return jobs, events, s3
