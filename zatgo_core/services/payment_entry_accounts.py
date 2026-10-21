"""Account Paid To (Receive) / Account Paid From (Pay) on a Payment Entry, from the chart of accounts.

ERPNext fills the field from the Mode of Payment's default account and lists every Bank *and* Cash
account whose Account Type is set. For a Bank mode of payment that leaves the field empty when the default
is missing or disabled, offers cash accounts, and hides a bank ledger that has no Account Type. With
ZG System Settings -> "Auto-fill Account Paid To / Paid From on Payment Entry" ticked (default):

- a Bank mode of payment fills the field with the mode's default account, else the company's default bank
  account, else the first ledger listed under "Bank Accounts" in the chart of accounts, and the picker offers
  only the "Bank Accounts" ledgers (the same definition the invoice Cash / Bank pickers use);
- every other mode keeps ERPNext's own default and list.

Unticked: the field stays blank until the user picks one, and the picker is ERPNext's.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from zatgo_core.services import payment_allocation

SETTINGS = "ZG System Settings"
FIELD = "autofill_payment_entry_account"


def autofill_enabled() -> bool:
    """get_single_value can't tell "never saved" from "unticked" (both 0), so read the row:
    no row yet means the field default, on."""
    rows = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, FIELD))
    return True if not rows else bool(cint(rows[0][0]))


def chart_ledgers(company: str, account_type: str, txt: str = "") -> list[tuple[str, str]]:
    """(name, currency) of every enabled ledger of the company that is of the Account Type or sits under a
    group of that type ("Cash In Hand", "Bank Accounts" in the chart), name order, through frappe.get_list
    so the user's own Account permissions still apply."""
    return [(r.name, r.account_currency) for r in _chart_rows(company, account_type, txt)]


def _chart_rows(company: str, account_type: str, txt: str = "") -> list:
    groups = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 1, "account_type": account_type},
        fields=["lft", "rgt"],
    )
    ledgers = frappe.get_list(
        "Account",
        filters={"company": company, "is_group": 0, "disabled": 0},
        or_filters={"name": ["like", f"%{txt}%"], "account_name": ["like", f"%{txt}%"]} if txt else None,
        fields=["name", "account_currency", "account_type", "lft"],
        order_by="name asc",
        limit_page_length=0,
    )
    return [r for r in ledgers if r.account_type == account_type or any(g.lft < r.lft < g.rgt for g in groups)]


def mode_type(mode_of_payment: str | None) -> str | None:
    return frappe.db.get_value("Mode of Payment", mode_of_payment, "type") if mode_of_payment else None


def default_bank_account(mode_of_payment: str, company: str) -> str | None:
    """The Bank Accounts ledger a Bank mode of payment starts with: its own default (or its first allowed
    account), then the company's default bank account, then the first ledger in chart order."""
    rows = _chart_rows(company, "Bank")
    if not rows:
        return None
    listed = {r.name for r in rows}
    for account in (a["account"] for a in payment_allocation.allowed_accounts(mode_of_payment, company)):
        if account in listed:
            return account
    company_default = frappe.db.get_value("Company", company, "default_bank_account")
    if company_default in listed:
        return company_default
    return min(rows, key=lambda r: r.lft).name


def resolve(mode_of_payment: str | None, company: str | None) -> dict:
    """What the form needs on picking a mode of payment: {enabled, mode_type, account}. `account` is set only
    for a Bank mode of payment; for any other mode the form defers to ERPNext's default."""
    enabled = autofill_enabled()
    kind = mode_type(mode_of_payment)
    account = default_bank_account(mode_of_payment, company) if enabled and kind == "Bank" and company else None
    return {"enabled": enabled, "mode_type": kind, "account": account}


def account_search(company: str, mode_of_payment: str | None, txt: str = "") -> list[tuple[str, str]]:
    """Rows for the Account Paid To / Paid From picker."""
    if autofill_enabled() and mode_type(mode_of_payment) == "Bank":
        return chart_ledgers(company, "Bank", txt)
    # ERPNext's own list for the bank / cash side of a Payment Entry
    return [
        (r[0], r[1])
        for r in frappe.get_list(
            "Account",
            filters={"company": company, "is_group": 0, "disabled": 0, "account_type": ["in", ["Bank", "Cash"]]},
            or_filters={"name": ["like", f"%{txt}%"], "account_name": ["like", f"%{txt}%"]} if txt else None,
            fields=["name", "account_currency"],
            order_by="name asc",
            limit_page_length=0,
            as_list=True,
        )
    ]
