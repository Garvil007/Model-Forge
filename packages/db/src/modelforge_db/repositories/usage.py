"""UsageRepository: monthly per-user usage counters, incremented atomically."""

from __future__ import annotations

from typing import Any

from ..client import get_table
from ..keys import usage_sk, user_pk
from ..records import UsageRecord


class UsageRepository:
    def __init__(self, table: Any = None) -> None:
        self._table = table if table is not None else get_table()

    def increment(
        self,
        user_id: str,
        year_month: str,
        *,
        jobs_run: int = 0,
        cpu_seconds: int = 0,
        gpu_seconds: int = 0,
    ) -> UsageRecord:
        response = self._table.update_item(
            Key={"PK": user_pk(user_id), "SK": usage_sk(year_month)},
            UpdateExpression=(
                "SET userId = :userId, yearMonth = :yearMonth "
                "ADD jobsRun :jobsRun, cpuSeconds :cpuSeconds, gpuSeconds :gpuSeconds"
            ),
            ExpressionAttributeValues={
                ":userId": user_id,
                ":yearMonth": year_month,
                ":jobsRun": jobs_run,
                ":cpuSeconds": cpu_seconds,
                ":gpuSeconds": gpu_seconds,
            },
            ReturnValues="ALL_NEW",
        )
        return _to_record(response["Attributes"])

    def get(self, user_id: str, year_month: str) -> UsageRecord:
        response = self._table.get_item(
            Key={"PK": user_pk(user_id), "SK": usage_sk(year_month)}
        )
        item = response.get("Item")
        if item is None:
            return UsageRecord(
                user_id=user_id, year_month=year_month, jobs_run=0, cpu_seconds=0, gpu_seconds=0
            )
        return _to_record(item)


def _to_record(item: dict[str, Any]) -> UsageRecord:
    return UsageRecord(
        user_id=item["userId"],
        year_month=item["yearMonth"],
        jobs_run=int(item.get("jobsRun", 0)),
        cpu_seconds=int(item.get("cpuSeconds", 0)),
        gpu_seconds=int(item.get("gpuSeconds", 0)),
    )
