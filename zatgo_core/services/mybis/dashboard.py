"""Dashboard payloads built from `queries`. Pure composition: no SQL here, no accounting rules beyond the documented formulas.

Every figure carries its previous-period value so the app never has to recompute anything; a figure the caller may not read is
`{"available": false}` rather than a zero.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.services.mybis import metrics, queries
from zatgo_core.services.mybis.scope import Scope

UNAVAILABLE = {"available": False}


def _can(kind: str) -> bool:
    return bool(frappe.has_permission(queries.SOURCE_DOCTYPES[kind], "read"))


def kpis(scope: Scope) -> dict[str, Any]:
    cur, prev = scope.current, scope.previous
    company = scope.company
    out: dict[str, Any] = {"currency": scope.currency}

    def pair(fn, *args):
        """(current, previous) of fn(company, from, to, *args); previous None when not compared."""
        c = fn(company, cur.from_date, cur.to_date, *args)
        p = fn(company, prev.from_date, prev.to_date, *args) if prev else None
        return c, p

    def get(d: dict | None, key: str):
        return None if d is None else d[key]

    # -- sales ------------------------------------------------------------------------------------------------------
    sales_c = sales_p = None
    if _can("sales"):
        sales_c, sales_p = pair(queries.sales_totals)
        out["total_sales"] = metrics.metric(sales_c["sales"], get(sales_p, "sales"))
        out["net_sales"] = metrics.metric(sales_c["net_sales"], get(sales_p, "net_sales"))
        out["sales_detail"] = {
            "returns": metrics.metric(sales_c["returns"], get(sales_p, "returns"), higher_is_better=False),
            "discount": metrics.metric(sales_c["discount"], get(sales_p, "discount"), higher_is_better=False),
            "invoices": metrics.metric(sales_c["invoices"], get(sales_p, "invoices")),
            "average_order_value": metrics.metric(sales_c["average_order_value"], get(sales_p, "average_order_value")),
        }
    else:
        out["total_sales"] = out["net_sales"] = dict(UNAVAILABLE)

    # -- ledger-based: COGS, expenses, net profit -------------------------------------------------------------------
    pnl_c = pnl_p = None
    if _can("gl"):
        pnl_c, pnl_p = pair(queries.gl_pnl)
        out["expenses"] = metrics.metric(pnl_c["expenses"], get(pnl_p, "expenses"), higher_is_better=False)
        out["net_profit"] = metrics.metric(pnl_c["net_profit"], get(pnl_p, "net_profit"))
    else:
        out["expenses"] = out["net_profit"] = dict(UNAVAILABLE)

    # -- gross profit: needs net sales and COGS (ledger when the company has perpetual inventory) ---------------------
    if sales_c is not None and (_can("gl") or not frappe.get_cached_value("Company", company, "enable_perpetual_inventory")):
        cogs_c, basis = queries.cogs(company, cur.from_date, cur.to_date, pnl_c["cogs"] if pnl_c else 0.0)
        cogs_p = None
        if prev:
            cogs_p, _basis = queries.cogs(company, prev.from_date, prev.to_date, pnl_p["cogs"] if pnl_p else 0.0)
        gp_c = sales_c["net_sales"] - cogs_c
        gp_p = None if cogs_p is None or sales_p is None else sales_p["net_sales"] - cogs_p
        out["cogs"] = metrics.metric(cogs_c, cogs_p, higher_is_better=False)
        out["gross_profit"] = metrics.metric(
            gp_c,
            gp_p,
            basis=basis,
            margin_percent=metrics.percent(gp_c, sales_c["net_sales"]),
            previous_margin_percent=None if gp_p is None else metrics.percent(gp_p, sales_p["net_sales"]),
        )
    else:
        out["cogs"] = out["gross_profit"] = dict(UNAVAILABLE)

    # -- purchases --------------------------------------------------------------------------------------------------
    if _can("purchases"):
        pur_c, pur_p = pair(queries.purchase_totals)
        out["purchases"] = metrics.metric(pur_c["net_purchases"], get(pur_p, "net_purchases"), higher_is_better=False)
    else:
        out["purchases"] = dict(UNAVAILABLE)

    # -- balances as of the end of each period ----------------------------------------------------------------------
    if _can("gl"):
        for key, account_type in (("receivables", "Receivable"), ("payables", "Payable")):
            c = queries.balance_as_of(company, account_type, cur.to_date)
            p = queries.balance_as_of(company, account_type, prev.to_date) if prev else None
            sign = 1 if account_type == "Receivable" else -1  # payables are credit balances
            out[key] = metrics.metric(sign * c, None if p is None else sign * p, higher_is_better=False, as_of=cur.to_date.isoformat())
    else:
        out["receivables"] = out["payables"] = dict(UNAVAILABLE)
    if _can("stock"):
        c = queries.stock_value_as_of(company, cur.to_date)
        p = queries.stock_value_as_of(company, prev.to_date) if prev else None
        out["stock_value"] = metrics.metric(c, p, as_of=cur.to_date.isoformat())
    else:
        out["stock_value"] = dict(UNAVAILABLE)
    return out


def sales_trend(scope: Scope, group_by: str | None) -> dict[str, Any]:
    bucket = group_by or metrics.auto_bucket(scope.current.days)
    if bucket not in ("day", "week", "month"):
        frappe.throw(frappe._("group_by must be day, week or month"), frappe.ValidationError)

    today = getdate(frappe.utils.today())

    def series(period):
        # Never plot the future: days after today are not "zero sales", they have not happened yet.
        end = min(period.to_date, today)
        if end < period.from_date:
            return []
        rows = queries.net_sales_by_bucket(scope.company, period.from_date, end, bucket)
        return metrics.fill_series(rows, period.from_date, end, bucket)

    return {
        "currency": scope.currency,
        "group_by": bucket,
        "current": series(scope.current),
        "previous": series(scope.previous) if scope.previous else None,
    }


def top_rankings(scope: Scope, by: str, limit: int, order: str = "revenue") -> dict[str, Any]:
    limit = max(1, min(int(limit or 5), 50))
    rows = queries.top_sales(scope.company, scope.current.from_date, scope.current.to_date, by, limit, order)
    total = queries.total_item_revenue(scope.company, scope.current.from_date, scope.current.to_date)
    codes = [r["code"] for r in rows]
    before = {}
    if scope.previous:
        before = queries.revenue_for(scope.company, scope.previous.from_date, scope.previous.to_date, by, codes)
    for r in rows:
        r["share_percent"] = metrics.percent(r["revenue"], total)
        r["previous_revenue"] = before.get(r["code"], 0.0) if scope.previous else None
        r["growth_percent"] = (
            None if r["previous_revenue"] is None else metrics.metric(r["revenue"], r["previous_revenue"])["growth_percent"]
        )
    return {"currency": scope.currency, "by": by, "order": order, "total_revenue": round(total, 2), "rows": rows}


# -- sales / purchase analytics screens ------------------------------------------------------------------------------


def sales_summary(scope: Scope) -> dict[str, Any]:
    """The Sales screen's header figures (same definitions as the dashboard, plus paid / credit split)."""
    cur, prev = scope.current, scope.previous

    def pair(fn):
        c = fn(scope.company, cur.from_date, cur.to_date)
        p = fn(scope.company, prev.from_date, prev.to_date) if prev else None
        return c, p

    c, p = pair(queries.sales_totals)

    def m(key: str, **kw):
        return metrics.metric(c[key], None if p is None else p[key], **kw)

    out: dict[str, Any] = {
        "currency": scope.currency,
        "gross_sales": m("sales"),
        "net_sales": m("net_sales"),
        "returns": m("returns", higher_is_better=False),
        "discount": m("discount", higher_is_better=False),
        "tax": m("tax"),
        "invoices": m("invoices"),
        "average_order_value": m("average_order_value"),
        "paid_sales": m("paid_sales"),
        "credit_sales": m("outstanding_sales", higher_is_better=False),
    }
    if _can("gl") or not frappe.get_cached_value("Company", scope.company, "enable_perpetual_inventory"):
        gl_c = queries.gl_pnl(scope.company, cur.from_date, cur.to_date)["cogs"] if _can("gl") else 0.0
        cogs_c, basis = queries.cogs(scope.company, cur.from_date, cur.to_date, gl_c)
        gp_c = c["net_sales"] - cogs_c
        gp_p = None
        if p is not None:
            gl_p = queries.gl_pnl(scope.company, prev.from_date, prev.to_date)["cogs"] if _can("gl") else 0.0
            gp_p = p["net_sales"] - queries.cogs(scope.company, prev.from_date, prev.to_date, gl_p)[0]
        out["gross_profit"] = metrics.metric(gp_c, gp_p, basis=basis, margin_percent=metrics.percent(gp_c, c["net_sales"]))
    else:
        out["gross_profit"] = dict(UNAVAILABLE)
    return out


def purchase_summary(scope: Scope) -> dict[str, Any]:
    cur, prev = scope.current, scope.previous
    c = queries.purchase_totals(scope.company, cur.from_date, cur.to_date)
    p = queries.purchase_totals(scope.company, prev.from_date, prev.to_date) if prev else None

    def m(key: str, **kw):
        return metrics.metric(c[key], None if p is None else p[key], **kw)

    out = {
        "currency": scope.currency,
        "total_purchases": m("purchases", higher_is_better=False),
        "returns": m("returns"),
        "net_purchases": m("net_purchases", higher_is_better=False),
        "invoices": m("invoices"),
        "suppliers": metrics.metric(
            queries.supplier_count(scope.company, cur.from_date, cur.to_date),
            queries.supplier_count(scope.company, prev.from_date, prev.to_date) if prev else None,
        ),
    }
    if _can("gl"):
        pay_c = -queries.balance_as_of(scope.company, "Payable", cur.to_date)
        pay_p = -queries.balance_as_of(scope.company, "Payable", prev.to_date) if prev else None
        out["outstanding_payables"] = metrics.metric(pay_c, pay_p, higher_is_better=False, as_of=cur.to_date.isoformat())
    else:
        out["outstanding_payables"] = dict(UNAVAILABLE)
    return out
