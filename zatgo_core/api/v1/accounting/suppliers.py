"""Accounting — Suppliers."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_supplier, list_suppliers
from zatgo_core.services.erpnext_writes import create_supplier, update_supplier


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_suppliers(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_supplier(name)


@frappe.whitelist()
def create(
    supplier_name: str,
    supplier_type: str | None = None,
    supplier_group: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    return create_supplier(
        supplier_name=supplier_name,
        supplier_type=supplier_type,
        supplier_group=supplier_group,
        email=email,
        phone=phone,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_supplier(name, values)
