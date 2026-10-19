"""c_safetensors: convert a PyTorch state_dict to safetensors.

The only source the catalog offers is `torch`. Unlike every other convert op in this
package, a bare state_dict is exactly what this one needs — no architecture required,
since safetensors stores named tensors, not a runnable graph (same reason there is nothing
to run a before/after comparison against: see `workers/ops/fp_cast.py`'s identical
"not measured" story for this format). Loaded with `torch.load(..., weights_only=True)`,
consistent with every other op in this project that touches an untrusted `torch` upload.

The common real-world failure mode this op guards against: a state_dict can hold tensors
that are *views* into shared storage (e.g. weight-tying, or a tensor sliced from a bigger
buffer) — `safetensors.torch.save_file` refuses to serialize those directly. Each tensor is
made contiguous and cloned before saving, which detaches it from any shared storage.
"""

from __future__ import annotations

from typing import Any

from modelforge_catalog.models import OperationSpec
from modelforge_db.repositories.job_events import JobEventRepository

from ._convert_common import ConvertContext, not_measured, run_convert_op


def _from_torch(ctx: ConvertContext) -> dict[str, str]:
    import torch
    from safetensors.torch import save_file

    state = torch.load(str(ctx.local_in), map_location="cpu", weights_only=True)
    tensors = {
        name: (value.contiguous().clone() if torch.is_tensor(value) else torch.as_tensor(value))
        for name, value in state.items()
    }
    save_file(tensors, str(ctx.local_out))
    return not_measured("a state_dict has no architecture to run")


_CASTERS = {
    "torch": _from_torch,
}


def run(
    *,
    user_id: str,
    job_id: str,
    model_id: str,
    params: dict[str, Any],
    operation: OperationSpec,
    control: Any,
    event_repo: JobEventRepository,
    **kwargs: Any,
) -> None:
    run_convert_op(
        user_id=user_id, job_id=job_id, model_id=model_id, params=params, operation=operation,
        control=control, event_repo=event_repo, casters=_CASTERS,
        tmp_prefix="mf-convert-safetensors-", **kwargs,
    )


__all__ = ["run"]
