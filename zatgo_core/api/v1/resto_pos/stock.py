"""Resto POS stock levels and adjustments (Bin read, Stock Entry write)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_admin_service as svc


@frappe.whitelist()
def list(
    warehouse: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
    search: str | None = None,
) -> dict[str, Any]:
    return svc.list_stock(warehouse, page, page_size, search=search)


@frappe.whitelist(methods=["POST"])
def adjust(item_code: str, qty: float | str, client_id: str, warehouse: str | None = None, reason: str | None = None) -> dict[str, Any]:
    return svc.adjust_stock(item_code, qty, client_id, warehouse, reason)
