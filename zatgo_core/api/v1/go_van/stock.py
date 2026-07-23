"""Go Van stock — Bin list + Stock Entry adjust + Material Transfer."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.go_van_service import adjust_stock, list_van_stock, transfer_stock


@frappe.whitelist()
def list(
    warehouse: str,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    return list_van_stock(warehouse=warehouse, page=page, page_size=page_size)


@frappe.whitelist()
def adjust(
    client_id: str,
    item_code: str,
    delta: float | str,
    warehouse: str,
    company: str | None = None,
) -> dict[str, Any]:
    return adjust_stock(
        client_id=client_id,
        item_code=item_code,
        delta=delta,
        warehouse=warehouse,
        company=company,
    )


@frappe.whitelist()
def transfer(
    client_id: str,
    item_code: str,
    qty: float | str,
    from_warehouse: str,
    to_warehouse: str,
    company: str | None = None,
) -> dict[str, Any]:
    return transfer_stock(
        client_id=client_id,
        item_code=item_code,
        qty=qty,
        from_warehouse=from_warehouse,
        to_warehouse=to_warehouse,
        company=company,
    )
