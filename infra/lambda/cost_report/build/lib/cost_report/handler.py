"""Daily EventBridge-triggered Lambda: emails yesterday's spend, grouped by the `mf:queue`
cost allocation tag (cpu/gpu/untagged), to the budget notification address via SES.

Cost Explorer only reports tags that have been *activated* as cost allocation tags in the
Billing console (or via `ce:UpdateCostAllocationTagsStatus`) — a one-time step outside CDK,
since CloudFormation has no resource for it. If `mf:queue` hasn't been activated yet (e.g.
right after first deploy — activation can take up to 24h to start appearing in Cost
Explorer), the group-by silently returns everything under "no mf:queue tag" instead of
splitting cpu/gpu; the email says so explicitly rather than presenting a misleading total.
See docs/COSTS.md.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3

_TAG_KEY = "mf:queue"


def _yesterday_range() -> tuple[str, str]:
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    return yesterday.isoformat(), today.isoformat()


def _fetch_cost_by_tag(start: str, end: str) -> dict[str, float]:
    ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is a global/us-east-1 API
    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "TAG", "Key": _TAG_KEY}],
    )
    totals: dict[str, float] = {}
    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            label = group["Keys"][0] or "untagged"
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            totals[label] = totals.get(label, 0.0) + amount
    return totals


def _render_body(start: str, totals: dict[str, float]) -> str:
    if not totals:
        return f"No AWS spend recorded for {start}."
    lines = [f"ModelForge spend for {start}:", ""]
    grand_total = 0.0
    for label, amount in sorted(totals.items(), key=lambda kv: kv[0]):
        lines.append(f"  {label}: ${amount:.4f}")
        grand_total += amount
    lines.append("")
    lines.append(f"Total: ${grand_total:.4f}")
    if len(totals) == 1:
        lines.append(
            "\nNote: all spend is under one tag group — if this looks wrong, confirm the "
            f"'{_TAG_KEY}' cost allocation tag is activated in Billing > Cost allocation tags "
            "(activation can take up to 24h to appear in Cost Explorer)."
        )
    return "\n".join(lines)


def handler(event: dict[str, Any] = None, context: Any = None) -> dict[str, Any]:
    start, end = _yesterday_range()
    totals = _fetch_cost_by_tag(start, end)
    body = _render_body(start, totals)

    recipient = os.environ["MF_BUDGET_NOTIFICATION_EMAIL"]
    ses = boto3.client("ses", region_name=os.environ.get("MF_AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=recipient,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": f"ModelForge spend for {start}"},
            "Body": {"Text": {"Data": body}},
        },
    )
    return {"start": start, "totals": totals}
