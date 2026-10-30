"""d_logit: response-based knowledge distillation — a small student learns to match the
teacher's output probabilities (soft targets via temperature `temp`, weighted against a
hard task loss by `alpha`). Thin wrapper around `_distill_common.run_distillation_op`,
which owns teacher loading, student construction, the KD training loop, and the
download -> build -> train -> measure -> upload -> job-status runner.
"""

from __future__ import annotations

from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from ._distill_common import run_distillation_op


def run(
    *, user_id: str, job_id: str, model_id: str, params: dict[str, Any],
    operation: OperationSpec, control: Any, event_repo: JobEventRepository,
    job_repo: Any = None, models_repo: Any = None, s3_client_override: Any = None,
) -> None:
    run_distillation_op(
        user_id=user_id, job_id=job_id, model_id=model_id, params=params, control=control,
        event_repo=event_repo, use_feature_matching=False, job_repo=job_repo,
        models_repo=models_repo, s3_client_override=s3_client_override,
    )


__all__ = ["run"]
