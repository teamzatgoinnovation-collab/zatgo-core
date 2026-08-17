"""Accounting — Payment Entry (receive / pay)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_document_pdf, get_payment_entry, list_payment_entries
from zatgo_core.services.erpnext_writes import (
    cancel_payment_entry,
    create_contra_entry,
    create_pay_payment,
    create_receive_payment,
    submit_payment_entry,
)
from zatgo_core.services.erpnext_writes import create_pay_advance as _create_pay_advance_service
from zatgo_core.services.erpnext_writes import create_receive_advance as _create_receive_advance_service


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    party_type: str | None = None,
    party: str | None = None,
) -> dict[str, Any]:
    return list_payment_entries(page=page, page_size=page_size, party_type=party_type, party=party)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_payment_entry(name)


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    return get_document_pdf("Payment Entry", name, print_format=print_format)


@frappe.whitelist()
def create_receive(
    sales_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_receive_payment(
        sales_invoice=sales_invoice,
        amount=amount,
        mode_of_payment=mode_of_payment,
        posting_date=posting_date,
        reference_no=reference_no,
        cost_center=cost_center,
        project=project,
        client_id=client_id,
    )


@frappe.whitelist()
def create_pay(
    purchase_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_pay_payment(
        purchase_invoice=purchase_invoice,
        amount=amount,
        mode_of_payment=mode_of_payment,
        posting_date=posting_date,
        reference_no=reference_no,
        cost_center=cost_center,
        project=project,
        client_id=client_id,
    )


@frappe.whitelist()
def create_contra(
    from_account: str,
    to_account: str,
    amount: float | str,
    posting_date: str | None = None,
    reference_no: str | None = None,
    remarks: str | None = None,
    company: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_contra_entry(
        from_account=from_account,
        to_account=to_account,
        amount=amount,
        posting_date=posting_date,
        reference_no=reference_no,
        remarks=remarks,
        company=company,
        cost_center=cost_center,
        project=project,
        client_id=client_id,
    )


@frappe.whitelist()
def create_receive_advance(
    party: str,
    amount: float | str,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    invoices: Any = None,
    company: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return _create_receive_advance_service(
        party=party,
        amount=amount,
        mode_of_payment=mode_of_payment,
        posting_date=posting_date,
        reference_no=reference_no,
        invoices=invoices,
        company=company,
        cost_center=cost_center,
        project=project,
        client_id=client_id,
    )


@frappe.whitelist()
def create_pay_advance(
    party: str,
    amount: float | str,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    invoices: Any = None,
    company: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return _create_pay_advance_service(
        party=party,
        amount=amount,
        mode_of_payment=mode_of_payment,
        posting_date=posting_date,
        reference_no=reference_no,
        invoices=invoices,
        company=company,
        cost_center=cost_center,
        project=project,
        client_id=client_id,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_payment_entry(name)


@frappe.whitelist()
def cancel(name: str) -> dict[str, Any]:
    return cancel_payment_entry(name)
