"""Accounting — Journal Entry."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import (
    get_document_pdf,
    get_journal_entry,
    list_accounts,
    list_cost_centers,
    list_journal_entries,
    map_journal_entry_doc,
)
from zatgo_core.services.erpnext_writes import (
    _amend_doc,
    cancel_journal_entry,
    create_journal_entry,
    create_split_pay,
    create_split_receive,
    submit_journal_entry,
)


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_journal_entries(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_journal_entry(name)


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    return get_document_pdf("Journal Entry", name, print_format=print_format)


@frappe.whitelist()
def create(
    accounts: str | list | None = None,
    company: str | None = None,
    posting_date: str | None = None,
    user_remark: str | None = None,
    voucher_type: str | None = None,
    reference_no: str | None = None,
    reference_date: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return create_journal_entry(
        accounts=accounts,
        company=company,
        posting_date=posting_date,
        user_remark=user_remark,
        voucher_type=voucher_type,
        reference_no=reference_no,
        reference_date=reference_date,
        client_id=client_id,
    )


@frappe.whitelist()
def create_split_receive_entry(
    party: str,
    lines: str | list | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    remarks: str | None = None,
    cost_center: str | None = None,
    company: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Receipt split across several cash/bank accounts in one entry (e.g. part
    cash, part card) — a Journal Entry with the customer's receivable account
    auto-resolved, not a Payment Entry (which only supports one account)."""
    return create_split_receive(
        party=party,
        lines=lines,
        posting_date=posting_date,
        reference_no=reference_no,
        remarks=remarks,
        cost_center=cost_center,
        company=company,
        client_id=client_id,
    )


@frappe.whitelist()
def create_split_pay_entry(
    party: str,
    lines: str | list | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    remarks: str | None = None,
    cost_center: str | None = None,
    company: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Payment split across several cash/bank accounts in one entry — a Journal
    Entry with the supplier's payable account auto-resolved."""
    return create_split_pay(
        party=party,
        lines=lines,
        posting_date=posting_date,
        reference_no=reference_no,
        remarks=remarks,
        cost_center=cost_center,
        company=company,
        client_id=client_id,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_journal_entry(name)


@frappe.whitelist()
def cancel(name: str) -> dict[str, Any]:
    return cancel_journal_entry(name)


@frappe.whitelist()
def amend(name: str) -> dict[str, Any]:
    return _amend_doc("Journal Entry", name, map_journal_entry_doc)


@frappe.whitelist()
def list_accounts_catalog(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return list_accounts(page=page, page_size=page_size)


@frappe.whitelist()
def list_cost_centers_catalog(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return list_cost_centers(page=page, page_size=page_size)
