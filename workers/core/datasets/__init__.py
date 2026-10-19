"""Validation/calibration dataset loaders.

Each loader parses one of the upload shapes accepted by `TASK_TYPE_INFO.accept`
(packages/catalog/src/modelforge_catalog/validation.py) and yields samples suitable for an
`core.evaluators` evaluator or the quantize_static calibration pass (Phase 4).
"""

from __future__ import annotations
