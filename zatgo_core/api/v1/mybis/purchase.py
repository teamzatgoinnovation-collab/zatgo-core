"""MyBis -- Purchases screen: summary, breakdown by supplier / product / category / warehouse, invoice list and detail."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.v1.mybis import _common
from zatgo_core.api.v1.mybis.sales import breakdown_detail
from zatgo_core.api.validators import parse_json_dict, parse_pagination, require_login
from zatgo_core.services.mybis import breakdown, dashboard, queries, scope

SIDE = "purchase"


@frappe.whitelist(methods=["GET", "POST"])
def summary(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    refresh: Any = 0,
) -> dict[str, Any]:
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare}
    return _common.run("purchase_summary", args, ("purchases",), dashboard.purchase_summary, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def breakdown_by(
    dimension: str = "supplier",
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    filters: Any = None,
    limit: int | str = 20,
    order: str = "revenue",
    refresh: Any = 0,
) -> dict[str, Any]:
    f = parse_json_dict(filters, "filters")
    breakdown.check(SIDE, dimension, f)
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare,
            "dimension": dimension, "filters": f, "limit": limit, "order": order}

    def build(s: scope.Scope) -> dict[str, Any]:
        cur = (s.current.from_date, s.current.to_date)
        prev = (s.previous.from_date, s.previous.to_date) if s.previous else None
        return {"currency": s.currency, **breakdown.breakdown(SIDE, s.company, cur, prev, dimension, f, int(limit), order)}

    return _common.run("purchase_breakdown", args, ("purchases",), build, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def invoices(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    filters: Any = None,
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    require_login()
    f = parse_json_dict(filters, "filters")
    s = scope.resolve_scope(company, preset, from_date, to_date, 0)
    queries.guard("purchases")
    breakdown.check(SIDE, None, f)
    page_i, size_i, _start = parse_pagination(page, page_size)
    rows, total = breakdown.invoices(SIDE, s.company, s.current.from_date, s.current.to_date, f, page_i, size_i)
    out = paginated(rows, page=page_i, page_size=size_i, total=total, sort="posting_date desc")
    out["meta"].update(s.meta())
    return out


@frappe.whitelist(methods=["GET", "POST"])
def invoice_detail(name: str) -> dict[str, Any]:
    require_login()
    return ok(breakdown_detail("Purchase Invoice", name))
