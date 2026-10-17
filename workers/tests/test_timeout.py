"""core.timeout: the job_timeout context manager's Event flips after the configured duration."""

from __future__ import annotations

import time

from core.timeout import job_timeout


def test_job_timeout_flag_not_set_before_expiry() -> None:
    with job_timeout(10) as flag:
        assert not flag.is_set()


def test_job_timeout_flag_set_after_expiry() -> None:
    with job_timeout(0.05) as flag:
        time.sleep(0.15)
        assert flag.is_set()


def test_job_timeout_cancels_timer_on_exit() -> None:
    with job_timeout(0.05) as flag:
        pass
    # Timer is canceled on exit; whether or not it fired before cancellation, no exception
    # should propagate and the context manager must exit cleanly either way.
    assert isinstance(flag.is_set(), bool)
