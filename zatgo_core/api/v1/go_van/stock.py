"""Go Van stock — Bin list + Stock Entry adjust + Material Transfer."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.validators import require_login
from zatgo_core.services.go_van_service import adjust_stock, list_van_stock, transfer_stock
from zatgo_core.services.van_sale_access import get_profile, is_vansale_admin


@frappe.whitelist()
def list(
    warehouse: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    require_login()
    wh = (warehouse or "").strip()
    if not is_vansale_admin():
        profile = get_profile()
        user_wh = (profile.get("warehouse") if profile else "") or ""
        if not user_wh:
            frappe.throw("No van warehouse assigned to your profile.", frappe.ValidationError)
        if wh and wh != user_wh:
            frappe.throw("Access denied: You can only view stock for your assigned warehouse.", frappe.PermissionError)
        wh = user_wh
    return list_van_stock(warehouse=wh, page=page, page_size=page_size)


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
        profile = get_profile()
        user_wh = (profile.get("warehouse") if profile else "") or ""
        if not user_wh:
            frappe.throw("No van warehouse assigned to your profile.", frappe.ValidationError)
        wh = user_wh
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
        profile = get_profile()
        user_wh = (profile.get("warehouse") if profile else "") or ""
        if not user_wh:
            frappe.throw("No van warehouse assigned to your profile.", frappe.ValidationError)
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
