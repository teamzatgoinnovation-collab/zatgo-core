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
    paid_now: Any = None,
    paid_method: str | None = None,
    payments: Any = None,
) -> dict[str, Any]:
    """items = [{item_code, item_name?, qty, rate}]. Idempotent on client_id.

    A sale the POS made offline passes offline=1 with sale_datetime (ISO 8601, the moment it was paid), offline_ref (the receipt
    number it printed), device_id and the receipt's expected_total / expected_tax; see services/offline_sale.py.

    method="credit" (when the site allows it) posts the sale to a named customer unpaid; `paid_now` + `paid_method` take a
    part payment at the till.

    payments=[{method, amount, reference?}] pays the sale with several modes of payment (split payment): the amounts
    must add up to the invoice total; `method` is then ignored."""
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
        paid_now=paid_now,
        paid_method=paid_method,
        payments=payments,
    )


@frappe.whitelist(methods=["POST"])
def collect(invoice: str, method: str, client_id: str, amount: Any = None) -> dict[str, Any]:
    """Take a (part) payment against a posted POS invoice that is still owing. Idempotent on client_id."""
    return svc.collect_payment(invoice, method, client_id, amount)


@frappe.whitelist()
def unpaid(customer: str | None = None, page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    """Posted POS invoices that still owe money (credit sales), oldest first."""
    return svc.unpaid_invoices(customer, page, page_size)
