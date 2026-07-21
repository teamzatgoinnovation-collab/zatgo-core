"""Accounting — Purchase Invoice (bills)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_purchase_invoice, list_purchase_invoices
from zatgo_core.services.erpnext_writes import create_purchase_invoice, submit_purchase_invoice


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_purchase_invoices(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_purchase_invoice(name)


@frappe.whitelist()
def create(
    supplier: str,
    items: str | list | None = None,
    company: str | None = None,
    posting_date: str | None = None,
    due_date: str | None = None,
    remarks: str | None = None,
) -> dict[str, Any]:
    return create_purchase_invoice(
        supplier=supplier,
        items=items,
        company=company,
        posting_date=posting_date,
        due_date=due_date,
        remarks=remarks,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_purchase_invoice(name)
