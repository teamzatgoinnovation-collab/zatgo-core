"""Warehouse items — ERPNext Item catalog."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_item, list_items
from zatgo_core.services.erpnext_writes import create_item, update_item


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List stock items."""
    return list_items(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_item(name)


@frappe.whitelist()
def create(
    item_code: str,
    item_name: str | None = None,
    item_group: str | None = None,
    stock_uom: str | None = None,
    standard_rate: float | int | str | None = None,
    is_stock_item: int | str | bool | None = 1,
) -> dict[str, Any]:
    return create_item(
        item_code=item_code,
        item_name=item_name,
        item_group=item_group,
        stock_uom=stock_uom,
        standard_rate=standard_rate,
        is_stock_item=is_stock_item,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_item(name, values)
