"""Retail POS customers (ERPNext Customer)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_admin_service as svc


@frappe.whitelist()
def list(
    search: str | None = None,
    page: int | str = 1,
    page_size: int | str = 50,
    modified_since: str | None = None,
    include_disabled: Any = None,
) -> dict[str, Any]:
    return svc.list_customers(search, page, page_size, modified_since, include_disabled)


@frappe.whitelist(methods=["POST"])
def upsert(customer_id: str | None = None, customer_name: str | None = None, phone: str | None = None, email: str | None = None, client_id: str | None = None, vat_number: str | None = None) -> dict[str, Any]:
    return svc.upsert_customer(customer_id, customer_name, phone, email, client_id, vat_number)


@frappe.whitelist()
def balance(customer: str) -> dict[str, Any]:
    """Outstanding balance and credit limit of one customer (shown at the till before a credit sale)."""
    from zatgo_core.services import retail_pos_service

    return retail_pos_service.customer_balance(customer)
