"""MyBis -- dashboard figures (read-only aggregates; see services/mybis/queries.py for what each one means)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.v1.mybis._common import run as _run
from zatgo_core.services.mybis import dashboard


@frappe.whitelist(methods=["GET", "POST"])
def kpis(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    refresh: Any = 0,
) -> dict[str, Any]:
    """Headline figures with the previous period's value and growth. A figure the user may not read is {available: false}."""
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare}
    return _run("kpis", args, (), dashboard.kpis, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def sales_trend(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    group_by: str | None = None,
    refresh: Any = 0,
) -> dict[str, Any]:
    """Net sales per day / week / month (auto by range) for the period and the previous one. Empty buckets are 0."""
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare, "group_by": group_by}
    return _run("sales_trend", args, ("sales",), lambda s: dashboard.sales_trend(s, group_by), refresh)


@frappe.whitelist(methods=["GET", "POST"])
def top_categories(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    limit: int | str = 5,
    refresh: Any = 0,
) -> dict[str, Any]:
    """Top item groups by net sales, with share of total and growth against the previous period."""
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare, "limit": limit}
    return _run("top_categories", args, ("sales",), lambda s: dashboard.top_rankings(s, "category", int(limit)), refresh)


@frappe.whitelist(methods=["GET", "POST"])
def top_products(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    limit: int | str = 5,
    order: str = "revenue",
    refresh: Any = 0,
) -> dict[str, Any]:
    """Top items by net sales (order=revenue) or units (order=quantity), with share and growth."""
    if order not in ("revenue", "quantity"):
        frappe.throw(frappe._("order must be revenue or quantity"), frappe.ValidationError)
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare, "limit": limit, "order": order}
    return _run("top_products", args, ("sales",), lambda s: dashboard.top_rankings(s, "product", int(limit), order), refresh)
