"""Accounting — ERPNext Quotation (sales quote / proposal)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_document_pdf, get_quotation, list_quotations, map_quotation_doc
from zatgo_core.services.erpnext_writes import (
    _amend_doc,
    cancel_quotation,
    create_quotation,
    create_sales_invoice_from_quotation,
    submit_quotation,
)


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20, customer: str | None = None) -> dict[str, Any]:
    return list_quotations(page=page, page_size=page_size, customer=customer)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_quotation(name)


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    return get_document_pdf("Quotation", name, print_format=print_format or "ZatGo Quotation")


@frappe.whitelist()
def create(
    customer: str,
    items: str | list | None = None,
    company: str | None = None,
    transaction_date: str | None = None,
    valid_till: str | None = None,
    terms: str | None = None,
    cost_center: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_quotation(
        customer=customer,
        items=items,
        company=company,
        transaction_date=transaction_date,
        valid_till=valid_till,
        terms=terms,
        cost_center=cost_center,
        client_id=client_id,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_quotation(name)


@frappe.whitelist()
def cancel(name: str) -> dict[str, Any]:
    return cancel_quotation(name)


@frappe.whitelist()
def amend(name: str) -> dict[str, Any]:
    return _amend_doc("Quotation", name, map_quotation_doc)


@frappe.whitelist()
def convert_to_invoice(name: str) -> dict[str, Any]:
    return create_sales_invoice_from_quotation(name)
