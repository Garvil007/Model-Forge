"""GET /catalog. Serves packages/catalog so the frontend stops shipping its own copy.

Unauthenticated: the catalog is static reference data, not user-specific or sensitive, and the
web app needs it before login.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from modelforge_catalog.export import build_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
def get_catalog() -> dict[str, Any]:
    return build_catalog()
