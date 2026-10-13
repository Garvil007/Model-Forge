"""Shared catalog of ModelForge compression and conversion operations."""

from .converts import CONVERTS
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
]
