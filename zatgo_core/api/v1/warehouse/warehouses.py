"""Warehouse locations — ERPNext Warehouse."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import list_warehouses
from zatgo_core.services.erpnext_writes import create_warehouse, update_warehouse


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List non-group warehouses."""
    return list_warehouses(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    from zatgo_core.api.response import ok
    from zatgo_core.api.validators import require_login, require_str

    require_login()
    require_str(name, "name")
    frappe.has_permission("Warehouse", "read", doc=name, throw=True)
    doc = frappe.get_doc("Warehouse", name)
    return ok(
        {
            "id": doc.name,
            "name": doc.warehouse_name or doc.name,
            "company": doc.company,
            "parent_warehouse": getattr(doc, "parent_warehouse", None),
            "disabled": int(doc.disabled or 0),
        },
        meta={"stub": False, "source": "Warehouse"},
    )


@frappe.whitelist()
def create(
    warehouse_name: str,
    company: str | None = None,
    parent_warehouse: str | None = None,
) -> dict[str, Any]:
    return create_warehouse(
        warehouse_name=warehouse_name,
        company=company,
        parent_warehouse=parent_warehouse,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_warehouse(name, values)
