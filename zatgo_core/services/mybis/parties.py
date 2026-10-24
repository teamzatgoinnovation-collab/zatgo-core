"""Customer / supplier analytics: activity counts, new vs returning, outstanding balances and rankings.

Revenue, profit and order counts reuse the sales / purchase breakdown (one definition of "net sales per customer"); outstanding
and overdue come from ERPNext's receivable / payable summary reports through `finance.aging`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from zatgo_core.services.mybis import breakdown, finance, metrics
from zatgo_core.services.mybis.scope import Scope

KINDS: dict[str, dict[str, Any]] = {
    "customer": {
        "side": "sales",
        "doc": "Sales Invoice",
        "doctype": "Customer",
        "party": "customer",
        "name_field": "customer_name",
        "aging": "receivable",
        "orders": {"revenue": "revenue", "profit": "profit", "orders": "invoices", "outstanding": None},
        "guard": ("sales", "gl"),
    },
    "supplier": {
        "side": "purchase",
        "doc": "Purchase Invoice",
        "doctype": "Supplier",
        "party": "supplier",
        "name_field": "supplier_name",
        "aging": "payable",
        "orders": {"revenue": "revenue", "orders": "invoices", "outstanding": None},
        "guard": ("purchases", "gl"),
    },
}


def cfg(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        frappe.throw(_("kind must be customer or supplier"), frappe.ValidationError)
    return KINDS[kind]


def _active(c: dict[str, Any], company: str, start: date, end: date) -> int:
    row = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT `{c['party']}`) FROM `tab{c['doc']}`
        WHERE docstatus = 1 AND is_return = 0 AND company = %(company)s AND posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    return int(row[0][0] or 0)


def _new(c: dict[str, Any], company: str, start: date, end: date) -> int:
    """Parties whose first-ever (non-return) invoice with this company falls in the period."""
    row = frappe.db.sql(
        f"""
        SELECT COUNT(*) FROM (
          SELECT `{c['party']}` AS p, MIN(posting_date) AS first_day FROM `tab{c['doc']}`
          WHERE docstatus = 1 AND is_return = 0 AND company = %(company)s GROUP BY `{c['party']}`
        ) t WHERE t.first_day BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": start, "end": end},
    )
    return int(row[0][0] or 0)


def summary(scope: Scope, kind: str) -> dict[str, Any]:
    c = cfg(kind)
    cur, prev = scope.current, scope.previous

    def counts(start: date, end: date) -> dict[str, int]:
        active = _active(c, scope.company, start, end)
        new = _new(c, scope.company, start, end)
        return {"active": active, "new": new, "returning": max(0, active - new)}

    now = counts(cur.from_date, cur.to_date)
    before = counts(prev.from_date, prev.to_date) if prev else None
    ag_now = finance.aging(scope, c["aging"])
    ag_prev = None
    if prev:
        from dataclasses import replace

        ag_prev = finance.aging(replace(scope, current=prev, previous=None), c["aging"])
    owing = [p for p in ag_now["parties"] if p["outstanding"] > 0]

    def m(key: str, **kw):
        return metrics.metric(now[key], None if before is None else before[key], **kw)

    return {
        "currency": scope.currency,
        "kind": kind,
        "active": m("active"),
        "new": m("new"),
        "returning": m("returning"),
        "with_outstanding": metrics.metric(len(owing), None if ag_prev is None else len([p for p in ag_prev["parties"] if p["outstanding"] > 0]), higher_is_better=False),
        "total_outstanding": metrics.metric(ag_now["outstanding"], None if ag_prev is None else ag_prev["outstanding"], higher_is_better=False, as_of=ag_now["as_of"]),
        "overdue": metrics.metric(
            round(sum(p["overdue"] for p in ag_now["parties"]), 2),
            None if ag_prev is None else round(sum(p["overdue"] for p in ag_prev["parties"]), 2),
            higher_is_better=False,
        ),
    }


def _names(c: dict[str, Any], codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = frappe.get_all(c["doctype"], filters={"name": ["in", codes]}, fields=["name", c["name_field"]], limit_page_length=0)
    return {r["name"]: r.get(c["name_field"]) or r["name"] for r in rows}


def ranking(scope: Scope, kind: str, order: str, limit: int) -> dict[str, Any]:
    c = cfg(kind)
    if order not in c["orders"]:
        frappe.throw(_("order must be one of {0}").format(", ".join(c["orders"])), frappe.ValidationError)
    limit = max(1, min(int(limit or 20), 100))
    cur = (scope.current.from_date, scope.current.to_date)
    prev = (scope.previous.from_date, scope.previous.to_date) if scope.previous else None
    ag = finance.aging(scope, c["aging"])
    owed = {p["party"]: p for p in ag["parties"]}
    side, dim = c["side"], c["party"]

    if order == "outstanding":
        top = sorted(ag["parties"], key=lambda p: (-p["outstanding"], p["party"]))[:limit]
        top = [p for p in top if p["outstanding"] > 0]
        codes = [p["party"] for p in top]
        cur_rows = {r["code"]: r for r in breakdown.rows(side, scope.company, *cur, dim, {}, limit=None, codes=codes)}
        prev_rows = {r["code"]: r for r in breakdown.rows(side, scope.company, *prev, dim, {}, limit=None, codes=codes)} if prev else {}
        total = breakdown.total_revenue(side, scope.company, *cur, dim, {})
        names = _names(c, codes)
        rows = []
        for p in top:
            r = cur_rows.get(p["party"])
            revenue = r["revenue"] if r else 0.0
            before = prev_rows.get(p["party"], {}).get("revenue", 0.0) if prev else None
            rows.append(
                {
                    "code": p["party"],
                    "name": (r or {}).get("name") or names.get(p["party"], p["party"]),
                    "revenue": revenue,
                    "invoices": r["invoices"] if r else 0,
                    "share_percent": metrics.percent(revenue, total),
                    "previous_revenue": before,
                    "growth_percent": None if before is None else metrics.metric(revenue, before)["growth_percent"],
                }
            )
    else:
        data = breakdown.breakdown(side, scope.company, cur, prev, dim, {}, limit, c["orders"][order])
        rows = data["rows"]
        total = data["total_revenue"]
    for r in rows:
        p = owed.get(r["code"])
        r["outstanding"] = p["outstanding"] if p else 0.0
        r["overdue"] = p["overdue"] if p else 0.0
        for k in ("category", "quantity"):
            r.pop(k, None)
    return {"currency": scope.currency, "kind": kind, "order": order, "total_revenue": round(total, 2), "rows": rows}
