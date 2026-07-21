"""Accounting — Customers."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_customer, list_customers
from zatgo_core.services.erpnext_writes import create_customer, update_customer


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_customers(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_customer(name)


@frappe.whitelist()
def create(
    customer_name: str,
    customer_type: str | None = None,
    customer_group: str | None = None,
    territory: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    return create_customer(
        customer_name=customer_name,
        customer_type=customer_type,
        customer_group=customer_group,
        territory=territory,
        email=email,
        phone=phone,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_customer(name, values)
