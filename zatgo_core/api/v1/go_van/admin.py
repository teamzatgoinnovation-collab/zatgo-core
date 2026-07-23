"""Go Van admin overview APIs."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.erpnext_reads import list_zg
from zatgo_core.services.van_sale_access import (
    is_vansale_admin,
    map_profile_row,
)


def _require_admin() -> None:
    require_login()
    if not is_vansale_admin():
        frappe.throw("Admin role required", frappe.PermissionError)


@frappe.whitelist()
def users(page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    """List enabled ZG Van Sale Profile rows for filter chips."""
    _require_admin()
    return list_zg(
        "ZG Van Sale Profile",
        fields=["name", "user", "warehouse", "vehicle", "route_title", "enabled"],
        page=page,
        page_size=page_size,
        filters={"enabled": 1},
        order_by="user asc",
        map_row=map_profile_row,
    )


@frappe.whitelist()
def summary(
    sales_user: str | None = None,
    warehouse: str | None = None,
    vehicle: str | None = None,
    route_title: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Today (or date) aggregate across vans for admin dashboard."""
    _require_admin()
    day = getdate(date) if date else getdate(today())
    day_s = str(day)

    trip_filters: dict[str, Any] = {}
    if sales_user:
        trip_filters["sales_user"] = sales_user
    if warehouse:
        trip_filters["warehouse"] = warehouse
    if vehicle:
        trip_filters["vehicle"] = vehicle
    if route_title:
        trip_filters["route_title"] = route_title

    trips = []
    if frappe.db.exists("DocType", "ZG Trip"):
        trips = frappe.get_all(
            "ZG Trip",
            filters=trip_filters,
            fields=[
                "name",
                "status",
                "sales_user",
                "warehouse",
                "vehicle",
                "route_title",
                "planned_at",
            ],
            limit_page_length=5000,
        )

    # Prefer planned_at date match; if missing planned_at, still count.
    def _on_day(t: dict[str, Any]) -> bool:
        planned = t.get("planned_at")
        if not planned:
            return True
        try:
            return str(getdate(planned)) == day_s
        except Exception:
            return True

    day_trips = [t for t in trips if _on_day(t)]
    stops_total = len(day_trips)
    stops_done = sum(1 for t in day_trips if (t.get("status") or "") == "Completed")

    si_filters: dict[str, Any] = {
        "docstatus": 1,
        "posting_date": day_s,
    }
    if sales_user:
        si_filters["owner"] = sales_user
    if warehouse and frappe.db.has_column("Sales Invoice", "set_warehouse"):
        si_filters["set_warehouse"] = warehouse

    invoices = frappe.get_all(
        "Sales Invoice",
        filters=si_filters,
        fields=["name", "grand_total", "owner", "customer", "set_warehouse"],
        limit_page_length=5000,
    )
    sales_total = sum(float(r.get("grand_total") or 0) for r in invoices)

    pe_filters: dict[str, Any] = {
        "docstatus": 1,
        "posting_date": day_s,
        "payment_type": "Receive",
    }
    if sales_user:
        pe_filters["owner"] = sales_user
    payments = frappe.get_all(
        "Payment Entry",
        filters=pe_filters,
        fields=["name", "paid_amount", "owner", "party"],
        limit_page_length=5000,
    )
    collections_total = sum(float(r.get("paid_amount") or 0) for r in payments)

    # Per-user rollup
    by_user: dict[str, dict[str, Any]] = {}

    def _bucket(uid: str) -> dict[str, Any]:
        if uid not in by_user:
            by_user[uid] = {
                "user": uid,
                "full_name": frappe.db.get_value("User", uid, "full_name") or uid,
                "stops_total": 0,
                "stops_done": 0,
                "sales_total": 0.0,
                "collections_total": 0.0,
                "orders_count": 0,
                "collections_count": 0,
            }
        return by_user[uid]

    for t in day_trips:
        uid = t.get("sales_user") or "Unassigned"
        b = _bucket(uid)
        b["stops_total"] += 1
        if (t.get("status") or "") == "Completed":
            b["stops_done"] += 1

    for inv in invoices:
        uid = inv.get("owner") or "Unassigned"
        b = _bucket(uid)
        b["sales_total"] += float(inv.get("grand_total") or 0)
        b["orders_count"] += 1

    for pe in payments:
        uid = pe.get("owner") or "Unassigned"
        b = _bucket(uid)
        b["collections_total"] += float(pe.get("paid_amount") or 0)
        b["collections_count"] += 1

    return ok(
        {
            "date": day_s,
            "stops_total": stops_total,
            "stops_done": stops_done,
            "sales_total": sales_total,
            "collections_total": collections_total,
            "orders_count": len(invoices),
            "collections_count": len(payments),
            "by_user": sorted(by_user.values(), key=lambda x: x["user"]),
        },
        meta={"source": "go_van.admin.summary"},
    )
