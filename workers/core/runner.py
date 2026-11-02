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


def _convert_gguf_op(**kwargs: Any) -> None:
    from ops import convert_gguf

    convert_gguf.run(**kwargs)


def _quantize_gguf_op(**kwargs: Any) -> None:
    from ops import quantize_gguf

    quantize_gguf.run(**kwargs)


def _quantize_gptq_op(**kwargs: Any) -> None:
    from ops import quantize_gptq

    quantize_gptq.run(**kwargs)


def _quantize_awq_op(**kwargs: Any) -> None:
    from ops import quantize_awq

    quantize_awq.run(**kwargs)


def _quantize_nf4_op(**kwargs: Any) -> None:
    from ops import quantize_nf4

    quantize_nf4.run(**kwargs)


def _prune_magnitude_op(**kwargs: Any) -> None:
    from ops import prune_magnitude

    prune_magnitude.run(**kwargs)


def _prune_structured_op(**kwargs: Any) -> None:
    from ops import prune_structured

    prune_structured.run(**kwargs)


def _prune_24_op(**kwargs: Any) -> None:
    from ops import prune_24

    prune_24.run(**kwargs)


def _prune_wanda_op(**kwargs: Any) -> None:
    from ops import prune_wanda

    prune_wanda.run(**kwargs)


def _lowrank_svd_op(**kwargs: Any) -> None:
    from ops import lowrank_svd

    lowrank_svd.run(**kwargs)


def _lowrank_tucker_op(**kwargs: Any) -> None:
    from ops import lowrank_tucker

    lowrank_tucker.run(**kwargs)


def _distill_response_op(**kwargs: Any) -> None:
    from ops import distill_response

    distill_response.run(**kwargs)


def _distill_feature_op(**kwargs: Any) -> None:
    from ops import distill_feature

    distill_feature.run(**kwargs)


def _distill_llm_op(**kwargs: Any) -> None:
    from ops import distill_llm

    distill_llm.run(**kwargs)


_OPS_BY_OPERATION_ID: dict[str, OpFunction] = {
    "q_int8_dyn": _quantize_dynamic_op,
    "q_fp16": _fp_cast_op,
    "q_bf16": _fp_cast_op,
    "q_int8_static": _quantize_static_op,
    "q_gguf": _quantize_gguf_op,
    "q_gptq": _quantize_gptq_op,
    "q_awq": _quantize_awq_op,
    "q_nf4": _quantize_nf4_op,
    "p_magnitude": _prune_magnitude_op,
    "p_structured": _prune_structured_op,
    "p_24": _prune_24_op,
    "p_wanda": _prune_wanda_op,
    "l_svd": _lowrank_svd_op,
    "l_tucker": _lowrank_tucker_op,
    "d_logit": _distill_response_op,
    "d_feature": _distill_feature_op,
    "d_llm": _distill_llm_op,
    "c_onnx": _convert_onnx_op,
    "c_tflite": _convert_tflite_op,
    "c_torchscript": _convert_torchscript_op,
    "c_savedmodel": _convert_savedmodel_op,
    "c_safetensors": _convert_safetensors_op,
    "c_openvino": _convert_openvino_op,
    "c_gguf": _convert_gguf_op,
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
    import sys

    from . import consumer

    # One-shot mode: a real AWS Batch job is a single container that runs to
    # completion and exits — it never polls a queue itself. The dispatcher Lambda
    # (infra/lambda/dispatcher) submits the original SQS message body as the Batch
    # job's `message` parameter (see batch_client.RealBatchJobClient.submit_job),
    # which infra/stacks/batch_stack.py's container COMMAND (not environment —
    # confirmed live that AWS Batch only resolves `Ref::` placeholders in the
    # command array, not in environment variable values, which left MF_JOB_MESSAGE
    # holding the literal unsubstituted string "Ref::message") passes through as
    # sys.argv[1]. Without this branch, `python -m core.runner` fell through to the
    # queue-consumer loop below, which exits 0 immediately when none of the three
    # queue env vars are set — the job record was never touched and the frontend
    # polled forever.
    _job_message = sys.argv[1] if len(sys.argv) > 1 else None
    if _job_message:
        consumer.handle_job_message(_job_message)
    else:
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
                "modelforge-workers: exactly one of MF_JOB_MESSAGE / "
                "MF_SYSTEM_JOBS_QUEUE_URL / MF_CPU_JOBS_QUEUE_URL / "
                f"MF_GPU_JOBS_QUEUE_URL must be set; found {len(_active)} queue(s)."
            )
        else:
            _queue_url, _handler = _active[0]
            consumer.run_forever(_queue_url, _handler)
