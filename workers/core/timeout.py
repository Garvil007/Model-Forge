"""Background timer a job's dispatch loop uses to detect it has overrun its time budget.

Python can't safely interrupt a running thread from another thread, so this doesn't kill
anything itself — it just flips an Event after `seconds`. Callers (JobControl.check(),
called between stages) poll the Event and raise JobTimeoutError themselves.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def job_timeout(seconds: float) -> Iterator[threading.Event]:
    expired = threading.Event()
    timer = threading.Timer(seconds, expired.set)
    timer.daemon = True
    timer.start()
    try:
        yield expired
    finally:
        timer.cancel()
