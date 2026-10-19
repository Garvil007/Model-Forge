"""Dispatches a real compression/conversion job to its operation's worker function.

Each op function has the signature:

    def run(
        *,
        user_id: str,
        job_id: str,
        model_id: str,
        params: dict[str, Any],
        operation: OperationSpec,
        control: JobControl,
        event_repo: JobEventRepository,
    ) -> None

An op is responsible for writing its own `JobEvent`s per stage and its own terminal
`JobRecord.update_progress(status="succeeded"|"failed", ...)` — the runner only handles the
cross-cutting stop conditions (cancel/timeout/spot-interruption) via `control.check()`,
which an op must call between stages.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from modelforge_catalog import OPERATIONS, job_messages
from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository
from modelforge_db.repositories.jobs import JobRepository

from .exceptions import JobCanceledError, JobTimeoutError, SpotInterruptedError
from .timeout import job_timeout

_OPERATIONS_BY_ID: dict[str, OperationSpec] = {op.id: op for op in OPERATIONS}
_TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}

OpFunction = Callable[..., None]


class JobControl:
    """Passed to a dispatched op so it can cooperatively stop between stages.

    Call `.check()` after each stage. It raises (in priority order) JobTimeoutError,
    SpotInterruptedError, or JobCanceledError if the job should stop now.
    """

    def __init__(self, user_id: str, job_id: str, job_repo: JobRepository, timeout_flag: Any) -> None:
        self.user_id = user_id
        self.job_id = job_id
        self._job_repo = job_repo
        self._timeout_flag = timeout_flag
        self._spot_simulated = False

    def check(self) -> None:
        if self._timeout_flag.is_set():
            raise JobTimeoutError(f"job {self.job_id!r} exceeded its time limit")
        if os.environ.get("MF_SIMULATE_SPOT_INTERRUPTION") == "1" and not self._spot_simulated:
            self._spot_simulated = True
            raise SpotInterruptedError(f"job {self.job_id!r} simulated spot interruption")
        if self._job_repo.get(self.user_id, self.job_id).status == "canceled":
            raise JobCanceledError(f"job {self.job_id!r} canceled")


def _quantize_dynamic_op(**kwargs: Any) -> None:
    from ops import quantize_dynamic

    quantize_dynamic.run(**kwargs)


def _fp_cast_op(**kwargs: Any) -> None:
    from ops import fp_cast

    fp_cast.run(**kwargs)


def _quantize_static_op(**kwargs: Any) -> None:
    from ops import quantize_static

    quantize_static.run(**kwargs)


def _convert_onnx_op(**kwargs: Any) -> None:
    from ops import convert_onnx

    convert_onnx.run(**kwargs)


def _convert_tflite_op(**kwargs: Any) -> None:
    from ops import convert_tflite

    convert_tflite.run(**kwargs)


def _convert_torchscript_op(**kwargs: Any) -> None:
    from ops import convert_torchscript

    convert_torchscript.run(**kwargs)


def _convert_savedmodel_op(**kwargs: Any) -> None:
    from ops import convert_savedmodel

    convert_savedmodel.run(**kwargs)


def _convert_safetensors_op(**kwargs: Any) -> None:
    from ops import convert_safetensors

    convert_safetensors.run(**kwargs)


def _convert_openvino_op(**kwargs: Any) -> None:
    from ops import convert_openvino

    convert_openvino.run(**kwargs)


_OPS_BY_OPERATION_ID: dict[str, OpFunction] = {
    "q_int8_dyn": _quantize_dynamic_op,
    "q_fp16": _fp_cast_op,
    "q_bf16": _fp_cast_op,
    "q_int8_static": _quantize_static_op,
    "c_onnx": _convert_onnx_op,
    "c_tflite": _convert_tflite_op,
    "c_torchscript": _convert_torchscript_op,
    "c_savedmodel": _convert_savedmodel_op,
    "c_safetensors": _convert_safetensors_op,
    "c_openvino": _convert_openvino_op,
}


def _queue_url_for(operation: OperationSpec) -> str | None:
    env_name = "MF_CPU_JOBS_QUEUE_URL" if operation.queue == "cpu" else "MF_GPU_JOBS_QUEUE_URL"
    return os.environ.get(env_name)


def _sqs_client() -> Any:
    import boto3

    return boto3.client(
        "sqs",
        region_name=os.environ.get("MF_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("MF_AWS_ENDPOINT_URL") or None,
    )


def _requeue(
    *,
    job_id: str,
    user_id: str,
    model_id: str,
    operation: OperationSpec,
    sqs_client: Any | None,
    queue_url: str | None,
) -> None:
    url = queue_url if queue_url is not None else _queue_url_for(operation)
    if not url:
        print(
            f"modelforge-workers: no queue URL configured for {operation.queue!r} jobs; "
            f"cannot requeue {job_id!r}"
        )
        return
    client = sqs_client if sqs_client is not None else _sqs_client()
    message = job_messages.build_message(
        job_id=job_id, user_id=user_id, model_id=model_id, operation_id=operation.id
    )
    client.send_message(QueueUrl=url, MessageBody=message)


def _handle_spot_interruption(
    *,
    jobs: JobRepository,
    user_id: str,
    job_id: str,
    model_id: str,
    operation: OperationSpec,
    sqs_client: Any | None,
    queue_url: str | None,
) -> None:
    current = jobs.get(user_id, job_id)
    if current.retry_count < 1:
        jobs.increment_retry_count(user_id, job_id)
        jobs.update_progress(user_id, job_id, status="queued", progress_percent=0)
        _requeue(
            job_id=job_id,
            user_id=user_id,
            model_id=model_id,
            operation=operation,
            sqs_client=sqs_client,
            queue_url=queue_url,
        )
    else:
        jobs.update_progress(
            user_id,
            job_id,
            status="failed",
            progress_percent=current.progress_percent,
            error={
                "code": "spot_interrupted",
                "message": "job was interrupted by Spot reclamation and already retried once",
            },
        )


def run_job(
    *,
    job_id: str,
    user_id: str,
    model_id: str,
    operation_id: str,
    job_repo: JobRepository | None = None,
    event_repo: JobEventRepository | None = None,
    sqs_client: Any | None = None,
    queue_url: str | None = None,
) -> None:
    jobs = job_repo if job_repo is not None else JobRepository()
    events = event_repo if event_repo is not None else JobEventRepository()

    record = jobs.get(user_id, job_id)
    if record.status in _TERMINAL_STATUSES:
        return  # idempotent: already handled (SQS redelivery or duplicate dispatch)

    operation = _OPERATIONS_BY_ID.get(operation_id)
    op_fn = _OPS_BY_OPERATION_ID.get(operation_id) if operation is not None else None
    if operation is None or op_fn is None:
        jobs.update_progress(
            user_id,
            job_id,
            status="failed",
            progress_percent=record.progress_percent,
            error={
                "code": "unsupported_operator",
                "message": f"operation {operation_id!r} has no worker implementation yet",
            },
        )
        return

    jobs.update_progress(user_id, job_id, status="running", progress_percent=0)

    timeout_seconds = float(os.environ.get("MF_JOB_TIMEOUT_SECONDS", 7200))
    with job_timeout(timeout_seconds) as timeout_flag:
        control = JobControl(user_id, job_id, jobs, timeout_flag)
        try:
            op_fn(
                user_id=user_id,
                job_id=job_id,
                model_id=model_id,
                params=record.params,
                operation=operation,
                control=control,
                event_repo=events,
            )
        except SpotInterruptedError:
            _handle_spot_interruption(
                jobs=jobs,
                user_id=user_id,
                job_id=job_id,
                model_id=model_id,
                operation=operation,
                sqs_client=sqs_client,
                queue_url=queue_url,
            )
        except JobCanceledError:
            events.append(user_id, job_id, stage="canceled", message="Canceled by user")
        except JobTimeoutError as error:
            jobs.update_progress(
                user_id,
                job_id,
                status="failed",
                progress_percent=record.progress_percent,
                error={"code": "timeout", "message": str(error)},
            )
        except Exception as error:  # noqa: BLE001 — op crashed unexpectedly, not via control.check()
            jobs.update_progress(
                user_id,
                job_id,
                status="failed",
                progress_percent=record.progress_percent,
                error={"code": "unknown", "message": str(error)},
            )


if __name__ == "__main__":
    from . import consumer

    _system_queue = os.environ.get("MF_SYSTEM_JOBS_QUEUE_URL")
    _cpu_queue = os.environ.get("MF_CPU_JOBS_QUEUE_URL")
    _gpu_queue = os.environ.get("MF_GPU_JOBS_QUEUE_URL")

    _configured = [
        (_system_queue, consumer.handle_message),
        (_cpu_queue, consumer.handle_job_message),
        (_gpu_queue, consumer.handle_job_message),
    ]
    _active = [(url, handler) for url, handler in _configured if url]
    if len(_active) != 1:
        print(
            "modelforge-workers: exactly one of MF_SYSTEM_JOBS_QUEUE_URL / "
            "MF_CPU_JOBS_QUEUE_URL / MF_GPU_JOBS_QUEUE_URL must be set; "
            f"found {len(_active)}."
        )
    else:
        _queue_url, _handler = _active[0]
        consumer.run_forever(_queue_url, _handler)
