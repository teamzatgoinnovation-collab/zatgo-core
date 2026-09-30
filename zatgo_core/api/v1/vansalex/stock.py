"""VanSaleX stock — Bin list + Stock Entry adjust + Material Transfer."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.vansalex_settings import allowed_warehouse, selectable_warehouses
from zatgo_core.services.vansalex_service import adjust_stock, list_van_stock, transfer_stock
from zatgo_core.services.van_sale_access import is_vansale_admin, require_own_warehouse


@frappe.whitelist()
def list(
    warehouse: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    require_login()
    wh = (warehouse or "").strip()
    if not is_vansale_admin():
        wh = allowed_warehouse(wh)
    return list_van_stock(warehouse=wh, page=page, page_size=page_size)


@frappe.whitelist()
def warehouses() -> dict[str, Any]:
    """Warehouses the caller may choose on an invoice (just their default
    unless VanSaleX Settings / their profile allow changing it)."""
    require_login()
    return ok(selectable_warehouses(), meta={"source": "Warehouse"})


@frappe.whitelist()
def adjust(
    client_id: str,
    item_code: str,
    delta: float | str,
    warehouse: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    require_login()
    wh = (warehouse or "").strip()
    if not is_vansale_admin():
        wh = require_own_warehouse(None)
    return adjust_stock(
        client_id=client_id,
        item_code=item_code,
        delta=delta,
        warehouse=wh,
        company=company,
    )


@frappe.whitelist()
def transfer(
    client_id: str,
    item_code: str,
    qty: float | str,
    from_warehouse: str | None = None,
    to_warehouse: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    require_login()
    from_wh = (from_warehouse or "").strip()
    to_wh = (to_warehouse or "").strip()
    if not is_vansale_admin():
        user_wh = require_own_warehouse(None)
        if from_wh and from_wh != user_wh and to_wh != user_wh:
            frappe.throw("Access denied: Transfer must involve your assigned warehouse.", frappe.PermissionError)
        if not from_wh:
            from_wh = user_wh
    return transfer_stock(
        client_id=client_id,
        item_code=item_code,
        qty=qty,
        from_warehouse=from_wh,
        to_warehouse=to_wh,
        company=company,
    )
