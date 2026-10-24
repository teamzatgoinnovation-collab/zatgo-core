"""MyBis -- Alerts and Insights: rule-based statements over real figures, each with its calculation, data and a drill-down target."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.v1.mybis import _common
from zatgo_core.services.mybis import insights


def _feed(company, preset, from_date, to_date, refresh) -> dict[str, Any]:
    # The previous period is always needed (every rule compares), so `compare` is not a parameter here.
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": 1}
    return _common.run("insights", args, (), insights.generate, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def feed(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, refresh: Any = 0) -> dict[str, Any]:
    """All alerts and insights for the period, most severe first. Each item: id, type (alert | insight), severity
    (critical | high | medium | low), title, description, metric, current / previous value, source, calculation, data rows, drill target."""
    return _feed(company, preset, from_date, to_date, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def summary(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, refresh: Any = 0) -> dict[str, Any]:
    """Counts by severity / type and the three most severe items (for a badge or a dashboard card)."""
    env = _feed(company, preset, from_date, to_date, refresh)
    data = env["data"]
    env["data"] = {
        "currency": data["currency"],
        "counts": data["counts"],
        "comparison_note": data["comparison_note"],
        "top": [{k: i[k] for k in ("id", "type", "severity", "title", "description", "drill")} for i in data["items"][:3]],
    }
    return env
