"""MyBis -- the daily report: one day's sales, purchases, money in and out, and receivable / payable balances."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import today

from zatgo_core.api.v1.mybis import _common
from zatgo_core.services.mybis import daily_report


@frappe.whitelist(methods=["GET", "POST"])
def report(company: str | None = None, date: str | None = None, refresh: Any = 0) -> dict[str, Any]:
    """The report for `date` (default today), each figure compared with the day before. Sections the caller may not read answer
    `{available: false}`; `receivable` / `payable` carry the balance at the end of the day and how much of it is overdue."""
    day = date or today()
    args = {"company": company, "preset": "custom", "from_date": day, "to_date": day, "compare": 1}
    return _common.run("daily_report", args, (), daily_report.build, refresh, ttl=120)
