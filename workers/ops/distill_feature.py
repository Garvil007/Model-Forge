"""d_feature: feature-based knowledge distillation — matches the teacher's response AND
one intermediate feature (via a small learned `nn.Linear` adapter), on top of the same
response-based KD loss `distill_response.py` uses. Thin wrapper around `_distill_common.
run_distillation_op(use_feature_matching=True)`; see that module's docstring for exactly
how the intermediate layer is chosen and which teacher formats support it.
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
        event_repo=event_repo, use_feature_matching=True, job_repo=job_repo,
        models_repo=models_repo, s3_client_override=s3_client_override,
    )


__all__ = ["run"]
