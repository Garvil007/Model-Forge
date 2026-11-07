from __future__ import annotations

import os
from unittest.mock import MagicMock

from cost_report.handler import handler


def test_sends_email_with_spend_by_tag(monkeypatch):
    os.environ["MF_BUDGET_NOTIFICATION_EMAIL"] = "me@example.com"
    ce = MagicMock()
    ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "Groups": [
                    {"Keys": ["mf:queue$cpu"], "Metrics": {"UnblendedCost": {"Amount": "0.05"}}},
                    {"Keys": ["mf:queue$gpu"], "Metrics": {"UnblendedCost": {"Amount": "0.30"}}},
                ]
            }
        ]
    }
    ses = MagicMock()

    def _fake_client(service_name, **kwargs):
        return ce if service_name == "ce" else ses

    monkeypatch.setattr("cost_report.handler.boto3.client", _fake_client)

    result = handler({})

    assert result["totals"] == {"mf:queue$cpu": 0.05, "mf:queue$gpu": 0.30}
    ses.send_email.assert_called_once()
    _, kwargs = ses.send_email.call_args
    assert kwargs["Source"] == "me@example.com"
    assert "0.0500" in kwargs["Message"]["Body"]["Text"]["Data"]
    assert "0.3000" in kwargs["Message"]["Body"]["Text"]["Data"]


def test_no_spend_sends_a_clear_zero_message(monkeypatch):
    os.environ["MF_BUDGET_NOTIFICATION_EMAIL"] = "me@example.com"
    ce = MagicMock()
    ce.get_cost_and_usage.return_value = {"ResultsByTime": [{"Groups": []}]}
    ses = MagicMock()
    monkeypatch.setattr(
        "cost_report.handler.boto3.client", lambda name, **kw: ce if name == "ce" else ses
    )

    handler({})

    _, kwargs = ses.send_email.call_args
    assert "No AWS spend recorded" in kwargs["Message"]["Body"]["Text"]["Data"]
