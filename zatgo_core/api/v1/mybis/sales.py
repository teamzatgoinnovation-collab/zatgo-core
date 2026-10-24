"""MyBis -- Sales screen: summary, breakdown by dimension, invoice list and invoice detail (the drill-down chain)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.v1.mybis import _common
from zatgo_core.api.validators import parse_json_dict, parse_pagination, require_login
from zatgo_core.services.mybis import breakdown, dashboard, queries, scope

SIDE = "sales"


@frappe.whitelist(methods=["GET", "POST"])
def summary(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    refresh: Any = 0,
) -> dict[str, Any]:
    """Gross / net sales, returns, discount, tax, invoices, average order, paid vs credit, gross profit -- with previous period."""
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare}
    return _common.run("sales_summary", args, ("sales",), dashboard.sales_summary, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def breakdown_by(
    dimension: str = "category",
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
    """Ranked rows by customer | product | category | warehouse | salesperson, optionally narrowed by `filters`
    ({"category": ..., "product": ..., "customer": ..., "warehouse": ...}) -- each drill-down step adds one filter."""
    f = parse_json_dict(filters, "filters")
    breakdown.check(SIDE, dimension, f)
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare,
            "dimension": dimension, "filters": f, "limit": limit, "order": order}

    def build(s: scope.Scope) -> dict[str, Any]:
        cur = (s.current.from_date, s.current.to_date)
        prev = (s.previous.from_date, s.previous.to_date) if s.previous else None
        return {"currency": s.currency, **breakdown.breakdown(SIDE, s.company, cur, prev, dimension, f, int(limit), order)}

    return _common.run("sales_breakdown", args, ("sales",), build, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def movers(
    dimension: str = "category",
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int | str = 5,
    refresh: Any = 0,
) -> dict[str, Any]:
    """What changed against the previous period: the rows that gained and lost the most (new and lost rows included)."""
    breakdown.check(SIDE, dimension, {})
    args = {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": 1,
            "dimension": dimension, "limit": limit}

    def build(s: scope.Scope) -> dict[str, Any]:
        cur = (s.current.from_date, s.current.to_date)
        prev = (s.previous.from_date, s.previous.to_date)
        return {"currency": s.currency, **breakdown.movers(SIDE, s.company, cur, prev, dimension, int(limit))}

    return _common.run("sales_movers", args, ("sales",), build, refresh)


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
    """Sales invoices of the period (newest first), narrowed by the same `filters`. Not cached: it is a list the user pages through."""
    require_login()
    f = parse_json_dict(filters, "filters")
    s = scope.resolve_scope(company, preset, from_date, to_date, 0)
    queries.guard(*("sales",))
    breakdown.check(SIDE, None, f)
    page_i, size_i, _start = parse_pagination(page, page_size)
    rows, total = breakdown.invoices(SIDE, s.company, s.current.from_date, s.current.to_date, f, page_i, size_i)
    out = paginated(rows, page=page_i, page_size=size_i, total=total, sort="posting_date desc")
    out["meta"].update(s.meta())
    return out


@frappe.whitelist(methods=["GET", "POST"])
def invoice_detail(name: str) -> dict[str, Any]:
    """One Sales Invoice for the drill-down's last step. ERPNext permission and the Company restriction apply."""
    require_login()
    return ok(breakdown_detail("Sales Invoice", name))


def breakdown_detail(doctype: str, name: str) -> dict[str, Any]:
    from zatgo_core.services import row_scope

    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    row_scope.require_company(doc.company)
    party = "customer" if doctype == "Sales Invoice" else "supplier"
    return {
        "doctype": doctype,
        "name": doc.name,
        "company": doc.company,
        "currency": doc.currency,
        "company_currency": frappe.get_cached_value("Company", doc.company, "default_currency"),
        "party": doc.get(party),
        "party_name": doc.get(f"{party}_name"),
        "posting_date": str(doc.posting_date),
        "status": doc.status,
        "is_return": bool(doc.is_return),
        "return_against": doc.return_against,
        "net_total": doc.net_total,
        "total_taxes_and_charges": doc.total_taxes_and_charges,
        "grand_total": doc.grand_total,
        "outstanding_amount": doc.outstanding_amount,
        "items": [
            {"item_code": i.item_code, "item_name": i.item_name, "qty": i.qty, "uom": i.uom, "rate": i.rate, "amount": i.amount}
            for i in doc.items
        ],
    }
