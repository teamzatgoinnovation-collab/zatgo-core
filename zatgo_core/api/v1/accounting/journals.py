"""Accounting — Journal Entry."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_journal_entry, list_accounts, list_journal_entries
from zatgo_core.services.erpnext_writes import create_journal_entry, submit_journal_entry


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_journal_entries(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_journal_entry(name)


@frappe.whitelist()
def create(
    accounts: str | list | None = None,
    company: str | None = None,
    posting_date: str | None = None,
    user_remark: str | None = None,
    voucher_type: str | None = None,
) -> dict[str, Any]:
    return create_journal_entry(
        accounts=accounts,
        company=company,
        posting_date=posting_date,
        user_remark=user_remark,
        voucher_type=voucher_type,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_journal_entry(name)


@frappe.whitelist()
def list_accounts_catalog(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return list_accounts(page=page, page_size=page_size)
