"""Numbers on the ZatGo ERP workspace: per document the count and the Grand Total, the top selling product and the
top category.

Counts: submitted documents only (not drafts, not cancelled), Grand Total in the company currency. Reads that can
use `frappe.get_list` do (permissions and User Permissions apply). The grouped item queries are SQL over the invoice
items, so they are scoped by hand to what the user may see:
- a user with any User Permission is limited to the documents `frappe.get_list` returns for them (customer, company,
  warehouse... restrictions) and, when they hold Item Group / Item permissions, to those items only (an Item Group
  includes its sub-groups). Such a user's document totals are then the net amount of their allowed lines, not the
  Grand Total of whole documents (a document can hold items they may not see);
- a user without User Permissions sees everything their roles allow (fast path, Company clause as before).
Products and categories come from Sales Invoices only; a Credit Note (negative lines) nets itself out.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate
from frappe.utils.nestedset import get_descendants_of

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


CHILD_TABLES = {
    "Sales Invoice": "tabSales Invoice Item",
    "Purchase Invoice": "tabPurchase Invoice Item",
    "Sales Order": "tabSales Order Item",
    "Purchase Order": "tabPurchase Order Item",
}


def _scope() -> dict[str, Any] | None:
    """What a user with User Permissions may see, or None for a user without any (fast path).

    `items_sql` is the item-line condition (Item Group incl. sub-groups, and Item permissions) or "" when none apply.
    """
    from frappe.permissions import get_user_permissions

    perms = get_user_permissions(frappe.session.user) or {}
    if not perms or set(perms) <= {"Company"}:
        return None  # nothing the fast path (get_list + Company clause) does not already apply
    groups: set[str] = set()
    for row in perms.get("Item Group", []):
        if row.get("doc"):
            groups.add(row["doc"])
            groups.update(get_descendants_of("Item Group", row["doc"], ignore_permissions=True) or [])
    items = {r["doc"] for r in perms.get("Item", []) if r.get("doc")}
    params: dict[str, Any] = {}
    parts = []
    if groups:
        params["zg_groups"] = tuple(sorted(groups))
        parts.append("it.item_group IN %(zg_groups)s")
    if items:
        params["zg_items"] = tuple(sorted(items))
        parts.append("it.item_code IN %(zg_items)s")
    return {"items_sql": f" AND ({' OR '.join(parts)})" if parts else "", "params": params, "item_restricted": bool(parts)}


def _visible_names(doctype: str, date_field: str, start) -> list[str]:
    """Names of the submitted documents the user may read (permissions and User Permissions applied by get_list)."""
    filters: list = [["docstatus", "=", 1]]
    if start:
        filters.append([date_field, ">=", start])
    return frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0)


def _scoped_totals(doctype: str, date_field: str, start, scope: dict[str, Any]) -> dict[str, Any]:
    names = _visible_names(doctype, date_field, start)
    if not names:
        return {"doctype": doctype, "count": 0, "total": 0.0}
    if not scope["item_restricted"]:  # restricted only by header fields: whole documents, Grand Total as ever
        rows = frappe.get_list(
            doctype,
            filters=[["name", "in", names]],
            fields=[{"COUNT": "name", "as": "count"}, {"SUM": "base_grand_total", "as": "total"}],
            limit_page_length=0,
        )
        row = rows[0] if rows else {}
        return {"doctype": doctype, "count": int(row.get("count") or 0), "total": float(row.get("total") or 0)}
    params = {"names": tuple(names), **scope["params"]}
    row = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT it.parent) AS c, SUM(it.base_net_amount) AS t
        FROM `{CHILD_TABLES[doctype]}` it
        WHERE it.parent IN %(names)s{scope["items_sql"]}
        """,
        params,
        as_dict=True,
    )[0]
    return {"doctype": doctype, "count": int(row.c or 0), "total": float(row.t or 0)}


def _doc_totals(doctype: str, date_field: str, start, scope: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not frappe.has_permission(doctype, "read"):
        return None
    if scope:
        return _scoped_totals(doctype, date_field, start, scope)
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


def _top(group_column: str, label_column: str, start, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Top sold by net amount over submitted Sales Invoices. group_column / label_column are fixed names, never user input."""
    params: dict[str, Any] = {"limit": TOP_N}
    date_sql = ""
    if start:
        date_sql = " AND si.posting_date >= %(start)s"
        params["start"] = start
    company_sql = row_scope.company_clause("si.company", params)
    if scope:  # User Permissions: only documents they may read, and only the items they may see
        names = _visible_names("Sales Invoice", "posting_date", start)
        if not names:
            return []
        params["zg_names"] = tuple(names)
        params.update(scope["params"])
        company_sql += " AND si.name IN %(zg_names)s" + scope["items_sql"]
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
    scope = _scope()
    return {
        "period": period,
        "currency": _currency(),
        "docs": [_doc_totals(dt, field, start, scope) or {"doctype": dt, "count": None, "total": None} for dt, field in DOCS],
        "top_products": _top("item_code", "item_name", start, scope) if can_sales else None,
        "top_categories": _top("item_group", "item_group", start, scope) if can_sales else None,
    }
