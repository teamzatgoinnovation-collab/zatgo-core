"""Warehouse stock — ERPNext Bin / Warehouse."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import list_stock, list_warehouses


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List stock balances (falls back to warehouses if bins empty)."""
    payload = list_stock(page=page, page_size=page_size)
    if payload.get("meta", {}).get("total", 0) == 0:
        return list_warehouses(page=page, page_size=page_size)
    return payload


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    """Get warehouse by name."""
    from zatgo_core.services.erpnext_reads import _get_doctype

    return _get_doctype(
        "Warehouse",
        name,
        map_doc=lambda d: {"id": d.name, "name": d.warehouse_name or d.name, "company": d.company},
    )
