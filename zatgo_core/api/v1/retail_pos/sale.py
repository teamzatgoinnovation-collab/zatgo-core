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
    offline: Any = None,
    sale_datetime: str | None = None,
    offline_ref: str | None = None,
    device_id: str | None = None,
    expected_total: Any = None,
    expected_tax: Any = None,
) -> dict[str, Any]:
    """items = [{item_code, item_name?, qty, rate}]. Idempotent on client_id.

    A sale the POS made offline passes offline=1 with sale_datetime (ISO 8601, the moment it was paid), offline_ref (the receipt
    number it printed), device_id and the receipt's expected_total / expected_tax; see services/offline_sale.py."""
    return svc.create_sale(
        items,
        method,
        client_id,
        customer_id,
        customer_name,
        customer_phone,
        discount_type,
        discount_value,
        offline=offline,
        sale_datetime=sale_datetime,
        offline_ref=offline_ref,
        device_id=device_id,
        expected_total=expected_total,
        expected_tax=expected_tax,
    )
