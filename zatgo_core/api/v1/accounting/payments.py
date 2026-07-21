"""Accounting — Payment Entry (receive / pay)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_payment_entry, list_payment_entries
from zatgo_core.services.erpnext_writes import (
    create_pay_payment,
    create_receive_payment,
    submit_payment_entry,
)


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_payment_entries(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_payment_entry(name)


@frappe.whitelist()
def create_receive(
    sales_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
) -> dict[str, Any]:
    return create_receive_payment(
        sales_invoice=sales_invoice,
        amount=amount,
        mode_of_payment=mode_of_payment,
        posting_date=posting_date,
        reference_no=reference_no,
    )


@frappe.whitelist()
def create_pay(
    purchase_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
) -> dict[str, Any]:
    return create_pay_payment(
        purchase_invoice=purchase_invoice,
        amount=amount,
        mode_of_payment=mode_of_payment,
        posting_date=posting_date,
        reference_no=reference_no,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_payment_entry(name)
