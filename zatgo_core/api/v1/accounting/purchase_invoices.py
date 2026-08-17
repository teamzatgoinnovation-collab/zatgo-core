"""Accounting — Purchase Invoice (bills)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_document_pdf, get_purchase_invoice, list_purchase_invoices
from zatgo_core.services.erpnext_writes import (
    cancel_purchase_invoice,
    create_purchase_invoice,
    create_purchase_return,
    submit_purchase_invoice,
)


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20, supplier: str | None = None) -> dict[str, Any]:
    return list_purchase_invoices(page=page, page_size=page_size, supplier=supplier)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_purchase_invoice(name)


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    return get_document_pdf("Purchase Invoice", name, print_format=print_format)


@frappe.whitelist()
def create(
    supplier: str,
    items: str | list | None = None,
    company: str | None = None,
    posting_date: str | None = None,
    due_date: str | None = None,
    remarks: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_purchase_invoice(
        supplier=supplier,
        items=items,
        company=company,
        posting_date=posting_date,
        due_date=due_date,
        remarks=remarks,
        client_id=client_id,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_purchase_invoice(name)


@frappe.whitelist()
def cancel(name: str) -> dict[str, Any]:
    return cancel_purchase_invoice(name)


@frappe.whitelist()
def create_return(
    return_against: str,
    items: str | list | None = None,
    reason: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_purchase_return(
        return_against=return_against, items=items, reason=reason, client_id=client_id
    )
