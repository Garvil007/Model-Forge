"""Shared catalog of ModelForge compression and conversion operations."""

from .availability import AvailabilityResult, check_availability
from .converts import CONVERTS
from .job_messages import InvalidJobMessageError, JobMessage
from .job_messages import build_message as build_job_message
from .job_messages import parse_message as parse_job_message
from .job_stages import StageDef, stages_for_operation
from .methods import METHODS
from .models import (
    ModelInfo,
    OperationSpec,
    ParamOption,
    ParamSpec,
    ShowIf,
    TechniqueInfo,
)
from .techniques import TECHNIQUES

OPERATIONS = METHODS + CONVERTS

__all__ = [
    "ModelInfo",
    "OperationSpec",
    "ParamOption",
    "ParamSpec",
    "ShowIf",
    "TechniqueInfo",
    "TECHNIQUES",
    "METHODS",
    "CONVERTS",
    "OPERATIONS",
    "AvailabilityResult",
    "check_availability",
    "JobMessage",
    "InvalidJobMessageError",
    "build_job_message",
    "parse_job_message",
    "StageDef",
    "stages_for_operation",
]
