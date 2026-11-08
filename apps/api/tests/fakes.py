"""Shared test doubles used across multiple router test modules."""

from __future__ import annotations


class FakeRateLimitRepository:
    """Always allows — router tests exercise business logic, not the limiter itself
    (see test_rate_limit.py for that). Never falls through to the real DynamoDB-backed
    RateLimitRepository, which would otherwise hit a real AWS table during `pytest`."""

    def increment_and_check(self, *args: object, **kwargs: object) -> bool:
        return True
