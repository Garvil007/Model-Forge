from __future__ import annotations

from typing import Any

from modelforge_db import BillingEventRepository

from .conftest import unique_id


def test_record_if_new_claims_an_event_once(table: Any) -> None:
    repo = BillingEventRepository(table)
    event_id = unique_id()

    assert repo.record_if_new(event_id) is True


def test_record_if_new_is_false_on_retry(table: Any) -> None:
    repo = BillingEventRepository(table)
    event_id = unique_id()
    repo.record_if_new(event_id)

    assert repo.record_if_new(event_id) is False


def test_different_events_are_independent(table: Any) -> None:
    repo = BillingEventRepository(table)

    assert repo.record_if_new(unique_id()) is True
    assert repo.record_if_new(unique_id()) is True
