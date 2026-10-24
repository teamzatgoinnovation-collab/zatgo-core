"""Sales / purchase analytics: breakdown by a dimension, invoice lists and the drill-down chain.

One query builder serves both sides. Dimension and filter names are an allow-list that maps to fixed SQL expressions -- a client
value is only ever a bound parameter, never part of the statement. Revenue is the item rows' `base_net_amount` (company currency,
before tax, returns negative), so a category / product / warehouse figure nets its returns off. Salesperson revenue is the invoice
net total split by the Sales Team's allocated percentage and cannot be combined with item-level filters.

Profit (sales only) = revenue - valuation cost of stock items sold (`incoming_rate` x `stock_qty`): an estimate "from valuation at
the time of sale", reported as such.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from zatgo_core.services.mybis import metrics

SIDES: dict[str, dict[str, Any]] = {
    "sales": {
        "doc": "Sales Invoice",
        "item": "Sales Invoice Item",
        "party": "customer",
        "party_name": "customer_name",
        "dims": ("customer", "product", "category", "warehouse", "salesperson"),
        "cost": "COALESCE(SUM(CASE WHEN it.is_stock_item = 1 THEN i.incoming_rate * i.stock_qty END), 0)",
        "guard": "sales",
    },
    "purchase": {
        "doc": "Purchase Invoice",
        "item": "Purchase Invoice Item",
        "party": "supplier",
        "party_name": "supplier_name",
        "dims": ("supplier", "product", "category", "warehouse"),
        "cost": None,
        "guard": "purchases",
    },
}

_WAREHOUSE = "COALESCE(NULLIF(i.warehouse, ''), '(none)')"
ITEM_LEVEL = {
    "product": ("i.item_code", "MAX(i.item_name)", "MAX(i.item_group)"),
    "category": ("i.item_group", "i.item_group", "NULL"),
    "warehouse": (_WAREHOUSE, _WAREHOUSE, "NULL"),
}
ITEM_FILTERS = {"product": "i.item_code", "category": "i.item_group", "warehouse": _WAREHOUSE}


def side(name: str) -> dict[str, Any]:
    if name not in SIDES:
        frappe.throw(_("Unknown side {0}").format(name), frappe.ValidationError)
    return SIDES[name]


def check(side_name: str, dimension: str | None, filters: dict[str, Any]) -> dict[str, Any]:
    cfg = side(side_name)
    allowed = set(cfg["dims"]) - {"salesperson"}
    if dimension is not None and dimension not in cfg["dims"]:
        frappe.throw(_("dimension must be one of {0}").format(", ".join(cfg["dims"])), frappe.ValidationError)
    bad = set(filters) - allowed
    if bad:
        frappe.throw(_("Unsupported filter(s): {0}").format(", ".join(sorted(bad))), frappe.ValidationError)
    if dimension == "salesperson" and set(filters) - {cfg["party"]}:
        frappe.throw(_("Salesperson figures can only be filtered by customer."), frappe.ValidationError)
    return cfg


def _filter_sql(cfg: dict[str, Any], filters: dict[str, Any], params: dict[str, Any]) -> str:
    out = ""
    for key, value in filters.items():
        if value in (None, ""):
            continue
        col = f"h.{cfg['party']}" if key == cfg["party"] else ITEM_FILTERS[key]
        params[f"f_{key}"] = value
        out += f" AND {col} = %(f_{key})s"
    return out


def _needs_items(dimension: str | None, filters: dict[str, Any], cfg: dict[str, Any]) -> bool:
    return dimension in ITEM_LEVEL or dimension == cfg["party"] or any(k in ITEM_FILTERS for k in filters)


def rows(
    side_name: str,
    company: str,
    start: date,
    end: date,
    dimension: str,
    filters: dict[str, Any],
    *,
    limit: int | None = 20,
    order: str = "revenue",
    codes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ranked rows of `dimension` for the period. `codes` restricts to those keys (used for the previous period)."""
    cfg = check(side_name, dimension, filters)
    params: dict[str, Any] = {"company": company, "start": start, "end": end}
    extra = _filter_sql(cfg, filters, params)
    if codes is not None:
        if not codes:
            return []
        params["codes"] = tuple(codes)
    # An alias of an aggregate cannot be used inside another expression in ORDER BY, so profit repeats the aggregates.
    revenue_agg = "COALESCE(SUM(i.base_net_amount), 0)"
    order_col = {
        "revenue": "revenue",
        "quantity": "quantity",
        "profit": f"({revenue_agg} - {cfg['cost'] or '0'})",
        "invoices": "invoices",
    }.get(order)
    if order_col is None:
        frappe.throw(_("Unsupported order"), frappe.ValidationError)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    if dimension == "salesperson":
        code_expr = "st.sales_person"
        in_clause = " AND st.sales_person IN %(codes)s" if codes is not None else ""
        sql = f"""
            SELECT {code_expr} AS code, {code_expr} AS name, NULL AS category,
                   COALESCE(SUM(h.base_net_total * st.allocated_percentage / 100), 0) AS revenue,
                   0 AS quantity, COUNT(DISTINCT CASE WHEN h.is_return = 0 THEN h.name END) AS invoices, 0 AS cost
            FROM `tabSales Invoice` h JOIN `tabSales Team` st ON st.parent = h.name AND st.parenttype = 'Sales Invoice'
            WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s {extra}{in_clause}
            GROUP BY {code_expr} HAVING revenue != 0 ORDER BY {order_col} DESC {limit_sql}
        """
    else:
        if dimension == cfg["party"]:
            code_expr, name_expr, cat_expr = f"h.{cfg['party']}", f"MAX(h.{cfg['party_name']})", "NULL"
        else:
            code_expr, name_expr, cat_expr = ITEM_LEVEL[dimension]
        in_clause = f" AND {code_expr} IN %(codes)s" if codes is not None else ""
        cost = cfg["cost"] or "0"
        sql = f"""
            SELECT {code_expr} AS code, {name_expr} AS name, {cat_expr} AS category,
                   COALESCE(SUM(i.base_net_amount), 0) AS revenue, COALESCE(SUM(i.stock_qty), 0) AS quantity,
                   COUNT(DISTINCT CASE WHEN h.is_return = 0 THEN h.name END) AS invoices, {cost} AS cost
            FROM `tab{cfg['item']}` i JOIN `tab{cfg['doc']}` h ON h.name = i.parent
            LEFT JOIN `tabItem` it ON it.name = i.item_code
            WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s {extra}{in_clause}
            GROUP BY {code_expr} HAVING revenue != 0 ORDER BY {order_col} DESC {limit_sql}
        """
    raw = frappe.db.sql(sql, params, as_dict=True)
    out = []
    for r in raw:
        revenue, cost_v = flt(r.revenue), flt(r.cost)
        row = {
            "code": r.code,
            "name": r.name or r.code,
            "category": r.category,
            "revenue": round(revenue, 2),
            "quantity": round(flt(r.quantity), 3),
            "invoices": int(r.invoices or 0),
        }
        if cfg["cost"] and dimension != "salesperson":
            row["cost"] = round(cost_v, 2)
            row["profit"] = round(revenue - cost_v, 2)
            row["margin_percent"] = metrics.percent(revenue - cost_v, revenue)
        out.append(row)
    return out


def total_revenue(side_name: str, company: str, start: date, end: date, dimension: str, filters: dict[str, Any]) -> float:
    cfg = check(side_name, dimension, filters)
    params: dict[str, Any] = {"company": company, "start": start, "end": end}
    extra = _filter_sql(cfg, filters, params)
    if dimension == "salesperson":
        sql = f"""
            SELECT COALESCE(SUM(h.base_net_total * st.allocated_percentage / 100), 0) AS t
            FROM `tabSales Invoice` h JOIN `tabSales Team` st ON st.parent = h.name AND st.parenttype = 'Sales Invoice'
            WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s {extra}
        """
    else:
        sql = f"""
            SELECT COALESCE(SUM(i.base_net_amount), 0) AS t
            FROM `tab{cfg['item']}` i JOIN `tab{cfg['doc']}` h ON h.name = i.parent
            WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s {extra}
        """
    return flt(frappe.db.sql(sql, params)[0][0])


def breakdown(
    side_name: str,
    company: str,
    current: tuple[date, date],
    previous: tuple[date, date] | None,
    dimension: str,
    filters: dict[str, Any],
    limit: int,
    order: str,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 100))
    ranked = rows(side_name, company, *current, dimension, filters, limit=limit, order=order)
    total = total_revenue(side_name, company, *current, dimension, filters)
    before: dict[str, float] = {}
    if previous:
        before = {r["code"]: r["revenue"] for r in rows(side_name, company, *previous, dimension, filters, limit=None, codes=[r["code"] for r in ranked])}
    for r in ranked:
        r["share_percent"] = metrics.percent(r["revenue"], total)
        r["previous_revenue"] = (before.get(r["code"], 0.0) if previous else None)
        r["growth_percent"] = None if r["previous_revenue"] is None else metrics.metric(r["revenue"], r["previous_revenue"])["growth_percent"]
    return {"side": side_name, "dimension": dimension, "filters": filters, "order": order, "total_revenue": round(total, 2), "rows": ranked}


def invoices(
    side_name: str, company: str, start: date, end: date, filters: dict[str, Any], page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    cfg = check(side_name, None, filters)
    params: dict[str, Any] = {"company": company, "start": start, "end": end}
    extra = _filter_sql(cfg, filters, params)
    item_level = any(k in ITEM_FILTERS for k in filters)
    amount = "COALESCE(SUM(i.base_net_amount), 0)" if item_level else "MAX(h.base_net_total)"
    join = f"JOIN `tab{cfg['item']}` i ON i.parent = h.name" if item_level else ""
    base = f"""
        FROM `tab{cfg['doc']}` h {join}
        WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s {extra}
    """
    total = int(frappe.db.sql(f"SELECT COUNT(DISTINCT h.name) {base}", params)[0][0] or 0)
    params.update({"limit": int(page_size), "offset": (int(page) - 1) * int(page_size)})
    raw = frappe.db.sql(
        f"""
        SELECT h.name, MAX(h.posting_date) AS posting_date, MAX(h.{cfg['party']}) AS party, MAX(h.{cfg['party_name']}) AS party_name,
               MAX(h.is_return) AS is_return, {amount} AS amount, MAX(h.base_grand_total) AS grand_total,
               MAX(h.outstanding_amount * h.conversion_rate) AS outstanding
        {base} GROUP BY h.name ORDER BY MAX(h.posting_date) DESC, h.name DESC LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
        as_dict=True,
    )
    return (
        [
            {
                "name": r.name,
                "posting_date": str(r.posting_date),
                "party": r.party,
                "party_name": r.party_name or r.party,
                "is_return": bool(r.is_return),
                "amount": round(flt(r.amount), 2),
                "grand_total": round(flt(r.grand_total), 2),
                "outstanding": round(flt(r.outstanding), 2),
            }
            for r in raw
        ],
        total,
    )
