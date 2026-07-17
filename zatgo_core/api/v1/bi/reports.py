"""BI reports catalog — available zatgo_core / ERPNext sources."""

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
        {
            "id": "items",
            "name": "Item Catalog",
            "app": "resto_pos",
            "reportMethod": "zatgo_core.api.v1.resto_pos.catalog.list",
            "fields": ["item_code", "item_name", "item_group", "standard_rate"],
            "rowCount": frappe.db.count("Item", {"disabled": 0}),
            "refreshedAt": frappe.utils.now_datetime().isoformat(),
        },
        {
            "id": "customers",
            "name": "Customers",
            "app": "crm_plus",
            "reportMethod": "zatgo_core.api.v1.crm.leads.list",
            "fields": ["name", "customer_name", "territory"],
            "rowCount": frappe.db.count("Customer", {"disabled": 0}),
            "refreshedAt": frappe.utils.now_datetime().isoformat(),
        },
        {
            "id": "invoices",
            "name": "Sales Invoices",
            "app": "finance_plus",
            "reportMethod": "zatgo_core.api.v1.accounting.invoices.list",
            "fields": ["name", "customer", "grand_total", "status"],
            "rowCount": frappe.db.count("Sales Invoice"),
            "refreshedAt": frappe.utils.now_datetime().isoformat(),
        },
    ]
    total = len(rows)
    sliced = rows[start : start + size_i]
    payload = paginated(sliced, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "stub": False}
    return payload


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    require_login()
    env = list(page=1, page_size=100)
    for row in env.get("data") or []:
        if row.get("id") == name:
            return ok(row, meta={"stub": False})
    return ok(None, meta={"stub": False, "message": "Not found"})
