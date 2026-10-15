"""Shared single-table DynamoDB repository layer for ModelForge. See docs/decisions.md."""

from __future__ import annotations

from .client import GSI1_NAME, TABLE_NAME, get_dynamodb_resource, get_kms_client, get_table
from .encryption import KmsEncryptor
from .exceptions import ModelForgeDbError, NotFoundError
from .records import (
    DatasetRecord,
    JobEventRecord,
    JobRecord,
    ModelRecord,
    UploadRecord,
    UsageRecord,
    UserRecord,
)
from .repositories.datasets import DatasetRepository
from .repositories.job_events import JobEventRepository
from .repositories.jobs import JobRepository
from .repositories.models import ModelRepository
from .repositories.uploads import UploadRepository
from .repositories.usage import UsageRepository
from .repositories.users import UserRepository

__all__ = [
    "TABLE_NAME",
    "GSI1_NAME",
    "get_dynamodb_resource",
    "get_kms_client",
    "get_table",
    "KmsEncryptor",
    "ModelForgeDbError",
    "NotFoundError",
    "UserRecord",
    "ModelRecord",
    "DatasetRecord",
    "JobRecord",
    "JobEventRecord",
    "UsageRecord",
    "UploadRecord",
    "UserRepository",
    "ModelRepository",
    "DatasetRepository",
    "JobRepository",
    "JobEventRepository",
    "UsageRepository",
    "UploadRepository",
]
