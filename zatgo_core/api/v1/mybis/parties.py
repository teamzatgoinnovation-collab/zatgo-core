"""MyBis -- Customers and Suppliers screens: activity, outstanding balances and rankings. A party's own breakdown / invoices use
the sales / purchase endpoints with a `customer` / `supplier` filter."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.v1.mybis import _common
from zatgo_core.services.mybis import parties


@frappe.whitelist(methods=["GET", "POST"])
def summary(kind: str = "customer", company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, compare: Any = 1, refresh: Any = 0) -> dict[str, Any]:
    """Active, new, returning parties, those with outstanding balances, total outstanding and overdue -- with the previous period."""
    c = parties.cfg(kind)
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare, "kind": kind}
    return _common.run("parties_summary", args, c["guard"], lambda s: parties.summary(s, kind), refresh)


@frappe.whitelist(methods=["GET", "POST"])
def ranking(kind: str = "customer", order: str = "revenue", company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, compare: Any = 1, limit: int | str = 20, refresh: Any = 0) -> dict[str, Any]:
    """Top parties by revenue | profit (customers) | orders | outstanding, each with outstanding and overdue amounts."""
    c = parties.cfg(kind)
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare, "kind": kind, "order": order, "limit": limit}
    return _common.run("parties_ranking", args, c["guard"], lambda s: parties.ranking(s, kind, order, int(limit)), refresh)
