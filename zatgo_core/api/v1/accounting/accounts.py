"""Accounting — Chart of Accounts (ERPNext Account)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_account_balance, list_chart_of_accounts
from zatgo_core.services.erpnext_writes import create_account, update_account


@frappe.whitelist()
def list(company: str | None = None) -> dict[str, Any]:
    """Full Account tree (groups + leaves) — not paginated, see service docstring."""
    return list_chart_of_accounts(company=company)


@frappe.whitelist()
def balance(account: str, date: str | None = None) -> dict[str, Any]:
    return get_account_balance(account, date=date)


@frappe.whitelist()
def create(
    account_name: str,
    parent_account: str,
    account_type: str | None = None,
    is_group: int | str | None = None,
    account_number: str | None = None,
    account_currency: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    return create_account(
        account_name=account_name,
        parent_account=parent_account,
        account_type=account_type,
        is_group=is_group,
        account_number=account_number,
        account_currency=account_currency,
        company=company,
    )


@frappe.whitelist()
def update(name: str, values: str | dict | None = None) -> dict[str, Any]:
    return update_account(name, values)
