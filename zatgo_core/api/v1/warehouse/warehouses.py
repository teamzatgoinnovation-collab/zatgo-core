"""Warehouse locations — ERPNext Warehouse."""

from __future__ import annotations

from typing import Any

from zatgo_core.services.erpnext_reads import list_warehouses


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List non-group warehouses."""
    return list_warehouses(page=page, page_size=page_size)
