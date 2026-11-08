from __future__ import annotations

from typing import Any

from modelforge_db import RateLimitRepository

from .conftest import unique_id


def test_allows_requests_up_to_the_limit(table: Any) -> None:
    repo = RateLimitRepository(table)
    key = unique_id()

    results = [
        repo.increment_and_check("test.scope", key, limit=3, window_seconds=60)
        for _ in range(3)
    ]

    assert results == [True, True, True]


def test_blocks_requests_once_the_limit_is_exceeded(table: Any) -> None:
    repo = RateLimitRepository(table)
    key = unique_id()

    for _ in range(3):
        repo.increment_and_check("test.scope", key, limit=3, window_seconds=60)

    assert repo.increment_and_check("test.scope", key, limit=3, window_seconds=60) is False


def test_different_keys_are_independent(table: Any) -> None:
    repo = RateLimitRepository(table)

    assert repo.increment_and_check("test.scope", unique_id(), limit=1, window_seconds=60) is True
    assert repo.increment_and_check("test.scope", unique_id(), limit=1, window_seconds=60) is True


def test_different_scopes_are_independent(table: Any) -> None:
    repo = RateLimitRepository(table)
    key = unique_id()

    assert repo.increment_and_check("scope.a", key, limit=1, window_seconds=60) is True
    assert repo.increment_and_check("scope.b", key, limit=1, window_seconds=60) is True


def test_a_new_window_resets_the_count(table: Any) -> None:
    repo = RateLimitRepository(table)
    key = unique_id()

    assert repo.increment_and_check("test.scope", key, limit=1, window_seconds=60, now=0) is True
    assert repo.increment_and_check("test.scope", key, limit=1, window_seconds=60, now=0) is False
    assert (
        repo.increment_and_check("test.scope", key, limit=1, window_seconds=60, now=61) is True
    )
