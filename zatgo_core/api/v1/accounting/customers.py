"""Accounting — Customers (list/get/create/update + offline sync bundle)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.customer_sync_service import get_customer_defaults, sync_customer_bundle
from zatgo_core.services.erpnext_reads import get_customer, list_customers
from zatgo_core.services.erpnext_writes import create_customer, update_customer


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_customers(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_customer(name)


@frappe.whitelist()
def defaults() -> dict[str, Any]:
    """Selling/Global defaults + pick lists for customer forms."""
    return get_customer_defaults()


@frappe.whitelist()
def create(
    customer_name: str | None = None,
    customer_type: str | None = None,
    customer_group: str | None = None,
    territory: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    client_id: str | None = None,
    customer: str | dict | None = None,
    contact: str | dict | None = None,
    address: str | dict | None = None,
    attachments: str | dict | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible create.

    - Simple args (customer_name, phone, …) → legacy create_customer
    - client_id + customer payload → full offline sync bundle
    """
    if client_id or customer:
        payload = customer
        if payload is None:
            payload = {
                "customer_name": customer_name,
                "customer_type": customer_type,
                "customer_group": customer_group,
                "territory": territory,
                "email": email,
                "mobile_no": phone,
            }
        return sync_customer_bundle(
            client_id=client_id or frappe.generate_hash(length=20),
            customer=payload,
            contact=contact,
            address=address,
            attachments=attachments,
        )

    return create_customer(
        customer_name=customer_name or "",
        customer_type=customer_type,
        customer_group=customer_group,
        territory=territory,
        email=email,
        phone=phone,
    )


@frappe.whitelist()
def sync(
    client_id: str,
    customer: str | dict | None = None,
    contact: str | dict | None = None,
    address: str | dict | None = None,
    attachments: str | dict | None = None,
) -> dict[str, Any]:
    """Idempotent Customer + Contact + Address + attachments sync."""
    return sync_customer_bundle(
        client_id=client_id,
        customer=customer,
        contact=contact,
        address=address,
        attachments=attachments,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_customer(name, values)
