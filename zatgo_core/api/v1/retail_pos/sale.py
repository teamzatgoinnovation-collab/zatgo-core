"""Retail POS checkout: one submitted Sales Invoice + Payment Entry per sale."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import retail_pos_service as svc


@frappe.whitelist(methods=["POST"])
def create(
    items: Any,
    method: str,
    client_id: str,
    customer_id: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    discount_type: str | None = None,
    discount_value: float | str | None = None,
) -> dict[str, Any]:
    """items = [{item_code, item_name?, qty, rate}]. Idempotent on client_id."""
    return svc.create_sale(
        items, method, client_id, customer_id, customer_name, customer_phone, discount_type, discount_value
    )
