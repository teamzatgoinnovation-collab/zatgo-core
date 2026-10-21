"""Payment Methods (Mode of Payment) and their allowed accounts.

Read-side helpers for the multi-method / multi-account payment rows on Sales
Invoice and Payment Entry (services/payment_allocation.py). Used by the Desk
forms' account pickers and by API clients building `payment_details`.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login, require_str
from zatgo_core.services import payment_allocation, payment_entry_accounts


@frappe.whitelist()
def methods(company: str) -> dict[str, Any]:
    """Enabled Modes of Payment with their allowed accounts (default first)."""
    require_login()
    company = require_str(company, "company")
    frappe.has_permission("Company", "read", doc=company, throw=True)
    rows = frappe.get_list(
        "Mode of Payment", filters={"enabled": 1}, fields=["name", "type"], order_by="name asc"
    )
    return ok(
        {
            "company": company,
            "methods": [
                {
                    "name": r.name,
                    "type": r.type,
                    "accounts": payment_allocation.allowed_accounts(r.name, company),
                }
                for r in rows
            ],
        }
    )


@frappe.whitelist()
def default_account(mode_of_payment: str, company: str) -> str | None:
    require_login()
    return payment_allocation.default_account(mode_of_payment, company)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def account_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field search: only the accounts allowed for the row's Mode of
    Payment and company, through frappe.get_list so the user's own Account
    permissions still apply."""
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}
    mode_of_payment = filters.get("mode_of_payment")
    company = filters.get("company")
    if not mode_of_payment or not company:
        return []
    allowed = [a["account"] for a in payment_allocation.allowed_accounts(mode_of_payment, company)]
    if not allowed:
        return []
    order = {name: i for i, name in enumerate(allowed)}
    rows = frappe.get_list(
        "Account",
        filters={"name": ["in", allowed]},
        or_filters={"name": ["like", f"%{txt}%"], "account_name": ["like", f"%{txt}%"]} if txt else None,
        fields=["name", "account_currency"],
        limit_start=start,
        limit_page_length=page_len,
        as_list=True,
    )
    return sorted(rows, key=lambda r: order.get(r[0], len(order)))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def payment_account_query(doctype, txt, searchfield, start, page_len, filters):
    """Cash Account / Bank Account picker on Sales and Purchase Invoice: every
    enabled ledger of the company that is of the given Account Type or sits
    under a group of that type ("Cash In Hand", "Bank Accounts" in the chart),
    through frappe.get_list so the user's Account permissions still apply."""
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}
    company = filters.get("company")
    account_type = filters.get("account_type")
    if not company or account_type not in ("Cash", "Bank"):
        return []
    rows = payment_entry_accounts.chart_ledgers(company, account_type, txt)
    return rows[int(start) : int(start) + int(page_len)]


@frappe.whitelist()
def payment_entry_account(mode_of_payment: str | None = None, company: str | None = None) -> dict:
    """Payment Entry form: the Bank Accounts ledger to pre-fill on picking a mode of payment (or none) --
    services/payment_entry_accounts.py."""
    require_login()
    return payment_entry_accounts.resolve(mode_of_payment, company)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def payment_entry_account_query(doctype, txt, searchfield, start, page_len, filters):
    """Account Paid To / Paid From picker on Payment Entry: the chart's Bank Accounts for a Bank mode of
    payment, ERPNext's bank / cash list otherwise (services/payment_entry_accounts.py)."""
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}
    company = filters.get("company")
    if not company:
        return []
    rows = payment_entry_accounts.account_search(company, filters.get("mode_of_payment"), txt)
    return rows[int(start) : int(start) + int(page_len)]
