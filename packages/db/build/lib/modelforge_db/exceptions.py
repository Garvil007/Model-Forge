"""Errors raised by the repository layer."""

from __future__ import annotations


class ModelForgeDbError(Exception):
    """Base error for the repository layer."""


class NotFoundError(ModelForgeDbError):
    """Item doesn't exist, or exists but isn't owned by the requesting user.

    Deliberately one error for both cases: a 403 (vs. 404) for someone else's
    item would confirm the item exists, leaking its existence across tenants.
    """
