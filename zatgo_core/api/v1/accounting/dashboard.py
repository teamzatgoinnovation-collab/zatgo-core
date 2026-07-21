"""Accounting dashboard aggregates."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import date_diff, flt, getdate, today

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login


def _empty_aging() -> dict[str, float]:
    return {
        "bucket_0_30": 0.0,
        "bucket_31_60": 0.0,
        "bucket_61_90": 0.0,
        "bucket_90_plus": 0.0,
    }


def _aging_from_rows(rows: list[Any], today_d: Any) -> dict[str, float]:
    aging = _empty_aging()
    for row in rows:
        amt = flt(row.outstanding_amount)
        if amt <= 0:
            continue
        due = getdate(row.due_date) if row.due_date else today_d
        days = max(0, date_diff(today_d, due))
        if days <= 30:
            aging["bucket_0_30"] += amt
        elif days <= 60:
            aging["bucket_31_60"] += amt
        elif days <= 90:
            aging["bucket_61_90"] += amt
        else:
            aging["bucket_90_plus"] += amt
    return aging


@frappe.whitelist()
def summary() -> dict[str, Any]:
    require_login()
    today_d = getdate(today())

    open_si = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "customer_name", "customer", "grand_total", "outstanding_amount", "due_date", "posting_date"],
        order_by="due_date asc",
        limit=10,
    )
    open_pi = frappe.get_all(
        "Purchase Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "supplier_name", "supplier", "grand_total", "outstanding_amount", "due_date", "posting_date"],
        order_by="due_date asc",
        limit=10,
    )

    ar_total = flt(
        frappe.db.sql(
            """
            select coalesce(sum(outstanding_amount), 0)
            from `tabSales Invoice`
            where docstatus = 1 and outstanding_amount > 0
            """
        )[0][0]
    )
    ap_total = flt(
        frappe.db.sql(
            """
            select coalesce(sum(outstanding_amount), 0)
            from `tabPurchase Invoice`
            where docstatus = 1 and outstanding_amount > 0
            """
        )[0][0]
    )

    overdue_ar = 0
    for row in frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", today_d]},
        fields=["outstanding_amount"],
    ):
        overdue_ar += flt(row.outstanding_amount)

    overdue_ap = 0
    for row in frappe.get_all(
        "Purchase Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", today_d]},
        fields=["outstanding_amount"],
    ):
        overdue_ap += flt(row.outstanding_amount)

    # Aging over all open invoices (not limited to the top-10 lists).
    ar_aging_rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["outstanding_amount", "due_date"],
    )
    ap_aging_rows = frappe.get_all(
        "Purchase Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["outstanding_amount", "due_date"],
    )

    recent_si = frappe.get_all(
        "Sales Invoice",
        fields=["name", "customer_name", "customer", "status", "grand_total", "posting_date"],
        order_by="modified desc",
        limit=5,
    )
    recent_pi = frappe.get_all(
        "Purchase Invoice",
        fields=["name", "supplier_name", "supplier", "status", "grand_total", "posting_date"],
        order_by="modified desc",
        limit=5,
    )

    return ok(
        {
            "ar_open": ar_total,
            "ap_open": ap_total,
            "ar_overdue": overdue_ar,
            "ap_overdue": overdue_ap,
            "sales_invoice_count": frappe.db.count("Sales Invoice"),
            "purchase_invoice_count": frappe.db.count("Purchase Invoice"),
            "ar_aging": _aging_from_rows(ar_aging_rows, today_d),
            "ap_aging": _aging_from_rows(ap_aging_rows, today_d),
            "open_receivables": [
                {
                    "id": r.name,
                    "name": r.name,
                    "party": r.customer_name or r.customer,
                    "amount": flt(r.grand_total),
                    "outstanding": flt(r.outstanding_amount),
                    "due_date": str(r.due_date) if r.due_date else None,
                }
                for r in open_si
            ],
            "open_payables": [
                {
                    "id": r.name,
                    "name": r.name,
                    "party": r.supplier_name or r.supplier,
                    "amount": flt(r.grand_total),
                    "outstanding": flt(r.outstanding_amount),
                    "due_date": str(r.due_date) if r.due_date else None,
                }
                for r in open_pi
            ],
            "recent_sales_invoices": [
                {
                    "id": r.name,
                    "name": r.name,
                    "party": r.customer_name or r.customer,
                    "status": r.status,
                    "amount": flt(r.grand_total),
                    "date": str(r.posting_date) if r.posting_date else None,
                }
                for r in recent_si
            ],
            "recent_purchase_invoices": [
                {
                    "id": r.name,
                    "name": r.name,
                    "party": r.supplier_name or r.supplier,
                    "status": r.status,
                    "amount": flt(r.grand_total),
                    "date": str(r.posting_date) if r.posting_date else None,
                }
                for r in recent_pi
            ],
        },
        meta={"stub": False, "source": "dashboard"},
    )
