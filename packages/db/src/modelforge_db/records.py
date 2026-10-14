"""Typed records returned by the repository layer (frozen — see coding-style.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    email: str
    plan: str
    settings: dict[str, Any]
    created_at: str
    updated_at: str
    hf_token_ciphertext: str | None = None


@dataclass(frozen=True)
class ModelRecord:
    user_id: str
    model_id: str
    filename: str
    s3_key: str
    size_bytes: int
    format: str
    family: str
    bits: int | None
    param_count: int | None
    details: dict[str, Any]
    status: str
    created_at: str
    updated_at: str
    ttl: int


@dataclass(frozen=True)
class DatasetRecord:
    user_id: str
    dataset_id: str
    kind: str
    filename: str
    s3_key: str
    size_bytes: int
    model_id: str | None
    created_at: str
    ttl: int


@dataclass(frozen=True)
class JobRecord:
    user_id: str
    job_id: str
    operation_id: str
    params: dict[str, Any]
    queue: str
    status: str
    progress_percent: int
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    timings: dict[str, Any]
    cost_estimate: float | None
    model_id: str | None
    created_at: str
    updated_at: str
    ttl: int


@dataclass(frozen=True)
class JobEventRecord:
    user_id: str
    job_id: str
    stage: str
    message: str
    percent: int | None
    timestamp_ms: int
    ttl: int


@dataclass(frozen=True)
class UsageRecord:
    user_id: str
    year_month: str
    jobs_run: int
    cpu_seconds: int
    gpu_seconds: int
