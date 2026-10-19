"""GET /datasets — list the caller's own uploaded calibration/validation datasets."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from modelforge_db.records import UserRecord
from modelforge_db.repositories.datasets import DatasetRepository

from ..auth import current_user
from ..services import serialize_dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])


def get_dataset_repository() -> DatasetRepository:
    return DatasetRepository()


@router.get("")
def list_datasets(
    user: Annotated[UserRecord, Depends(current_user)],
    datasets: Annotated[DatasetRepository, Depends(get_dataset_repository)],
) -> list[dict[str, Any]]:
    return [serialize_dataset(record) for record in datasets.list_for_user(user.user_id)]
