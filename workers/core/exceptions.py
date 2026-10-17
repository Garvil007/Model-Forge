"""Control-flow exceptions a dispatched op raises to tell the runner to stop between stages."""

from __future__ import annotations


class JobCanceledError(Exception):
    """Raised by JobControl.check() when the user has canceled the job."""


class JobTimeoutError(Exception):
    """Raised by JobControl.check() when the job's configured time limit has elapsed."""


class SpotInterruptedError(Exception):
    """Raised by JobControl.check() when the worker's compute was (or is simulated to be)
    reclaimed by a Spot interruption."""
