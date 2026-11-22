"""Numbers on the ZatGo ERP workspace: per document the count and the Grand Total, the top selling product and the
top category.

Counts: submitted documents only (not drafts, not cancelled), Grand Total in the company currency. Reads that can
use `frappe.get_list` do (permissions and User Permissions apply); the two grouped item queries are SQL over the
invoice items, limited to the user's Companies (`row_scope.company_clause`) and to users who may read Sales Invoice.
Products and categories come from Sales Invoices only; a Credit Note (negative lines) nets itself out.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.services import row_scope

PERIODS = ("month", "year", "all")
TOP_N = 5

# (DocType, date field) in the order the workspace shows them
DOCS = (
    ("Sales Invoice", "posting_date"),
    ("Purchase Invoice", "posting_date"),
    ("Sales Order", "transaction_date"),
    ("Purchase Order", "transaction_date"),
)


def period_start(period: str):
    """First day of the period, or None for all time."""
    today = getdate()
    if period == "month":
        return today.replace(day=1)
    if period == "year":
        return today.replace(month=1, day=1)
    return None


def _doc_totals(doctype: str, date_field: str, start) -> dict[str, Any] | None:
    if not frappe.has_permission(doctype, "read"):
        return None
    filters: list = [["docstatus", "=", 1]]
    if start:
        filters.append([date_field, ">=", start])
    rows = frappe.get_list(
        doctype,
        filters=filters,
        fields=[{"COUNT": "name", "as": "count"}, {"SUM": "base_grand_total", "as": "total"}],
        limit_page_length=0,
    )
    row = rows[0] if rows else {}
    return {"doctype": doctype, "count": int(row.get("count") or 0), "total": float(row.get("total") or 0)}


def _top(group_column: str, label_column: str, start) -> list[dict[str, Any]]:
    """Top sold by net amount over submitted Sales Invoices. group_column / label_column are fixed names, never user input."""
    params: dict[str, Any] = {"limit": TOP_N}
    date_sql = ""
    if start:
        date_sql = " AND si.posting_date >= %(start)s"
        params["start"] = start
    company_sql = row_scope.company_clause("si.company", params)
    rows = frappe.db.sql(
        f"""
        SELECT it.{group_column} AS name, MAX(it.{label_column}) AS label,
               SUM(it.base_net_amount) AS amount, SUM(it.qty) AS qty
        FROM `tabSales Invoice Item` it
        JOIN `tabSales Invoice` si ON si.name = it.parent
        WHERE si.docstatus = 1 AND IFNULL(it.{group_column}, '') != ''{date_sql}{company_sql}
        GROUP BY it.{group_column}
        HAVING SUM(it.base_net_amount) > 0
        ORDER BY amount DESC
        LIMIT %(limit)s
        """,
        params,
        as_dict=True,
    )
    return [
        {"name": r.name, "label": r.label or r.name, "amount": float(r.amount or 0), "qty": float(r.qty or 0)} for r in rows
    ]


def _currency() -> str | None:
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    return frappe.db.get_value("Company", company, "default_currency") if company else None


def summary(period: str = "all") -> dict[str, Any]:
    """Counts + totals per document and the top products / categories for `period` (month | year | all)."""
    if period not in PERIODS:
        period = "all"
    start = period_start(period)
    can_sales = frappe.has_permission("Sales Invoice", "read")
    return {
        "period": period,
        "currency": _currency(),
        "docs": [_doc_totals(dt, field, start) or {"doctype": dt, "count": None, "total": None} for dt, field in DOCS],
        "top_products": _top("item_code", "item_name", start) if can_sales else None,
        "top_categories": _top("item_group", "item_group", start) if can_sales else None,
    }
