"""Go Van AR aging — wraps Sales Invoice outstanding buckets."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import date_diff, flt, getdate, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.van_sale_access import is_vansale_admin


def _bucket_key(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "d_1_30"
    if days <= 60:
        return "d_31_60"
    if days <= 90:
        return "d_61_90"
    if days <= 120:
        return "d_91_120"
    return "d_120_plus"


def _empty_buckets() -> dict[str, float]:
    return {
        "current": 0.0,
        "d_1_30": 0.0,
        "d_31_60": 0.0,
        "d_61_90": 0.0,
        "d_91_120": 0.0,
        "d_120_plus": 0.0,
        "total": 0.0,
        "overdue": 0.0,
    }


@frappe.whitelist()
def summary(
    customer: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    """Aging summary buckets across open Sales Invoices."""
    require_login()
    today_d = getdate(today())
    filters: dict[str, Any] = {"docstatus": 1, "outstanding_amount": [">", 0]}
    if customer:
        filters["customer"] = customer
    if company:
        filters["company"] = company
    elif not is_vansale_admin():
        # Field users see all open AR they can read (ERPNext perm); no owner filter on SI aging
        pass

    rows = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "outstanding_amount",
            "grand_total",
            "posting_date",
            "due_date",
            "company",
        ],
        limit_page_length=5000,
    )
    buckets = _empty_buckets()
    by_customer: dict[str, dict[str, Any]] = {}

    for r in rows:
        amt = flt(r.outstanding_amount)
        if amt <= 0:
            continue
        due = getdate(r.due_date) if r.due_date else getdate(r.posting_date) or today_d
        days = date_diff(today_d, due)
        key = _bucket_key(days)
        buckets[key] += amt
        buckets["total"] += amt
        if days > 0:
            buckets["overdue"] += amt

        uid = r.customer or "Unknown"
        if uid not in by_customer:
            by_customer[uid] = {
                "customer": uid,
                "customer_name": r.customer_name or uid,
                **_empty_buckets(),
                "invoice_count": 0,
            }
        b = by_customer[uid]
        b[key] += amt
        b["total"] += amt
        if days > 0:
            b["overdue"] += amt
        b["invoice_count"] += 1

    customers = sorted(by_customer.values(), key=lambda x: -flt(x["overdue"]))
    return ok(
        {
            "as_of": str(today_d),
            "buckets": buckets,
            "customers": customers[:200],
            "customer_count": len(customers),
        },
        meta={"source": "go_van.aging.summary"},
    )


@frappe.whitelist()
def detail(
    customer: str | None = None,
    company: str | None = None,
    page: int | str = 1,
    page_size: int | str = 50,
) -> dict[str, Any]:
    """Invoice-level aging detail for drill-down."""
    require_login()
    today_d = getdate(today())
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"docstatus": 1, "outstanding_amount": [">", 0]}
    if customer:
        filters["customer"] = customer
    if company:
        filters["company"] = company

    total = frappe.db.count("Sales Invoice", filters)
    rows = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "outstanding_amount",
            "grand_total",
            "posting_date",
            "due_date",
            "company",
            "status",
        ],
        order_by="due_date asc, posting_date asc",
        start=start,
        page_length=size_i,
    )
    data = []
    for r in rows:
        due = getdate(r.due_date) if r.due_date else getdate(r.posting_date) or today_d
        days = date_diff(today_d, due)
        credit_limit = flt(frappe.db.get_value("Customer", r.customer, "credit_limit") or 0)
        data.append(
            {
                "name": r.name,
                "id": r.name,
                "customer": r.customer,
                "customer_name": r.customer_name,
                "outstanding": flt(r.outstanding_amount),
                "grand_total": flt(r.grand_total),
                "posting_date": str(r.posting_date or ""),
                "due_date": str(r.due_date or ""),
                "days_overdue": max(0, days),
                "bucket": _bucket_key(days),
                "company": r.company,
                "status": r.status,
                "credit_limit": credit_limit,
            }
        )
    payload = paginated(data, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "source": "go_van.aging.detail", "as_of": str(today_d)}
    return payload
