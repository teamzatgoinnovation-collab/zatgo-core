"""VanSaleX stock — Bin list + Stock Entry adjust + Material Transfer."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.vansalex_access import require as require_access
from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.vansalex_settings import allowed_warehouse, selectable_warehouses
from zatgo_core.services.vansalex_stock_rules import assert_transfer, assert_writeoff
from zatgo_core.services.vansalex_service import adjust_stock, list_van_stock, transfer_stock
from zatgo_core.services.van_sale_access import is_vansale_admin, require_own_warehouse


@frappe.whitelist()
def list(
    warehouse: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    require_login()
    require_access("inventory", "sales_invoice", "products", "dashboard", "my_performance")
    wh = (warehouse or "").strip()
    if not is_vansale_admin():
        wh = allowed_warehouse(wh)
    return list_van_stock(warehouse=wh, page=page, page_size=page_size)


@frappe.whitelist()
def warehouses() -> dict[str, Any]:
    """Warehouses the caller may choose on an invoice (just their default
    unless VanSaleX Settings / their profile allow changing it)."""
    require_login()
    require_access("sales_invoice", "inventory")
    return ok(selectable_warehouses(), meta={"source": "Warehouse"})


@frappe.whitelist()
def adjust(
    client_id: str,
    item_code: str,
    delta: float | str,
    warehouse: str | None = None,
    company: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Stock reconciliation on a warehouse. Admins: any warehouse, either
    direction. Field users (services/vansalex_stock_rules.py): their own van,
    a decrease only, within the Max Write-off Qty, and only with the
    `inventory.adjust` feature."""
    require_login()
    require_access("inventory")
    wh = (warehouse or "").strip()
    if not is_vansale_admin():
        # Blank = the van; another warehouse is refused (it used to be
        # silently swapped for the van, booking the stock somewhere unasked).
        wh = require_own_warehouse(wh)
        assert_writeoff(wh, delta)
    return adjust_stock(
        client_id=client_id,
        item_code=item_code,
        delta=delta,
        warehouse=wh,
        company=company,
        reason=reason,
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
    """Material Transfer between warehouses. Admins: any pair. Field users
    (services/vansalex_stock_rules.py): between their own van and a warehouse
    ticked "VanSaleX Transfer Point" (a blank from_warehouse is the van), and
    only with the `inventory.transfer` feature."""
    require_login()
    require_access("inventory")
    from_wh = (from_warehouse or "").strip()
    to_wh = (to_warehouse or "").strip()
    if not is_vansale_admin():
        user_wh = require_own_warehouse(None)
        if not from_wh:
            from_wh = user_wh
        assert_transfer(from_wh, to_wh)
    return transfer_stock(
        client_id=client_id,
        item_code=item_code,
        qty=qty,
        from_warehouse=from_wh,
        to_warehouse=to_wh,
        company=company,
    )
