"""ZatGo POS catalog — ERPNext Item."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_item, list_items


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List sellable items for POS."""
    return list_items(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    """Get one Item by name/code."""
    return get_item(name)
