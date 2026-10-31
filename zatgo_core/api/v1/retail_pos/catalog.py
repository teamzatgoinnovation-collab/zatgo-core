"""Retail POS catalog -- ERPNext Item (same behaviour as resto_pos.catalog)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_item, list_items


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_items(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_item(name)


@frappe.whitelist(methods=["POST"])
def upsert(
    item_code: str | None = None,
    item_name: str | None = None,
    price: float | str | None = None,
    item_group: str | None = None,
    barcode: str | None = None,
    uom: str | None = None,
    enabled: int | str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services import resto_pos_admin_service as svc

    return svc.upsert_item(item_code, item_name, price, item_group, barcode, uom, enabled)


@frappe.whitelist(methods=["POST"])
def disable(item_code: str) -> dict[str, Any]:
    from zatgo_core.services import resto_pos_admin_service as svc

    return svc.disable_item(item_code)


@frappe.whitelist()
def by_barcode(code: str) -> dict[str, Any]:
    from zatgo_core.services import resto_pos_admin_service as svc

    return svc.find_by_barcode(code)
