"""Warehouse items — ERPNext Item catalog + offline sync."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_item, list_items
from zatgo_core.services.erpnext_writes import create_item, update_item
from zatgo_core.services.item_sync_ops import sync_item_op
from zatgo_core.services.item_sync_service import get_item_defaults, sync_item_bundle


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
def defaults() -> dict[str, Any]:
    """Stock/Selling defaults + pick lists for product forms."""
    return get_item_defaults()


@frappe.whitelist()
def create(
    item_code: str | None = None,
    item_name: str | None = None,
    item_group: str | None = None,
    stock_uom: str | None = None,
    standard_rate: float | int | str | None = None,
    is_stock_item: int | str | bool | None = 1,
    client_id: str | None = None,
    item: str | dict | None = None,
    attachments: str | dict | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible create.

    - Simple args → legacy create_item
    - client_id + item payload → full offline sync bundle
    """
    if client_id or item:
        payload = item
        if payload is None:
            payload = {
                "item_code": item_code,
                "item_name": item_name,
                "item_group": item_group,
                "stock_uom": stock_uom,
                "selling_rate": standard_rate,
                "is_stock_item": is_stock_item,
            }
        return sync_item_bundle(
            client_id=client_id or frappe.generate_hash(length=20),
            item=payload,
            attachments=attachments,
        )

    return create_item(
        item_code=item_code or "",
        item_name=item_name,
        item_group=item_group,
        stock_uom=stock_uom,
        standard_rate=standard_rate,
        is_stock_item=is_stock_item,
    )


@frappe.whitelist()
def sync(
    client_id: str,
    item: str | dict | None = None,
    attachments: str | dict | None = None,
    op: str = "create",
    base_modified: str | None = None,
    force: int | str | bool | None = 0,
) -> dict[str, Any]:
    """Idempotent Item sync with optional update/delete + conflict check."""
    return sync_item_op(
        client_id=client_id,
        op=op,
        item=item,
        attachments=attachments,
        base_modified=base_modified,
        force=force,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_item(name, values)
