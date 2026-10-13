import pytest

from core.runner import UnknownOperationError, run_job


def test_run_job_accepts_known_operation() -> None:
    result = run_job({"job_id": "j1", "operation_id": "q_fp16"})
    assert result["operation_id"] == "q_fp16"
    assert result["status"] == "not_implemented"


def test_run_job_rejects_unknown_operation() -> None:
    with pytest.raises(UnknownOperationError):
        run_job({"job_id": "j2", "operation_id": "does_not_exist"})
