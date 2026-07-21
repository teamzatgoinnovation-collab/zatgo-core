"""Warehouse items — ERPNext Item catalog."""

from __future__ import annotations

from typing import Any

from zatgo_core.services.erpnext_reads import list_items


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List stock items."""
    return list_items(page=page, page_size=page_size)
