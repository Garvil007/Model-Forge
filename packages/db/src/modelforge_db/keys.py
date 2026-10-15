"""Key-builder helpers for the single-table schema. See docs/decisions.md."""

from __future__ import annotations


def user_pk(user_id: str) -> str:
    return f"USER#{user_id}"


def profile_sk() -> str:
    return "PROFILE"


def model_sk(model_id: str) -> str:
    return f"MODEL#{model_id}"


def dataset_sk(dataset_id: str) -> str:
    return f"DATASET#{dataset_id}"


def upload_sk(upload_id: str) -> str:
    return f"UPLOAD#{upload_id}"


def job_sk(job_id: str) -> str:
    return f"JOB#{job_id}"


def usage_sk(year_month: str) -> str:
    return f"USAGE#{year_month}"


def job_event_pk(user_id: str, job_id: str) -> str:
    return f"USER#{user_id}#JOB#{job_id}"


def job_event_sk(timestamp_ms: int, unique_suffix: str) -> str:
    return f"EVENT#{timestamp_ms:020d}#{unique_suffix}"


def email_gsi1pk(email: str) -> str:
    return f"EMAIL#{email.lower()}"


def gsi1sk_for_listing(entity_tag: str, created_at: str, entity_id: str) -> str:
    return f"{entity_tag}#{created_at}#{entity_id}"
