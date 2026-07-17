"""Admin overview — aggregated ERPNext counts."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    require_login()
    page_i, size_i, start = parse_pagination(page, page_size)
    rows = [
        {"id": "items", "name": "Items", "count": frappe.db.count("Item", {"disabled": 0})},
        {"id": "customers", "name": "Customers", "count": frappe.db.count("Customer", {"disabled": 0})},
        {"id": "leads", "name": "Leads", "count": frappe.db.count("Lead")},
        {"id": "employees", "name": "Employees", "count": frappe.db.count("Employee") if frappe.db.exists("DocType", "Employee") else 0},
        {"id": "sales_orders", "name": "Sales Orders", "count": frappe.db.count("Sales Order")},
        {"id": "purchase_orders", "name": "Purchase Orders", "count": frappe.db.count("Purchase Order")},
        {"id": "sales_invoices", "name": "Sales Invoices", "count": frappe.db.count("Sales Invoice")},
    ]
    total = len(rows)
    sliced = rows[start : start + size_i]
    payload = paginated(sliced, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "stub": False, "source": "overview"}
    return payload


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    require_login()
    env = list(page=1, page_size=100)
    for row in env.get("data") or []:
        if row.get("id") == name:
            return ok(row, meta={"stub": False})
    return ok(None, meta={"stub": False, "message": "Not found"})
