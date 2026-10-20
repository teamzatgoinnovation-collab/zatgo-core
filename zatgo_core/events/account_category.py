"""New Accounts inherit their parent's Account Category.

ERPNext's Financial Report Templates (Standard Balance Sheet (IFRS), Horizontal Balance Sheet, ...)
pick accounts by Account.account_category. A ledger added under "Cash In Hand" / "Bank Accounts" /
... without one is skipped by the template, so TOTAL ASSETS falls short of TOTAL LIABILITIES AND
EQUITY while the default (template-less) Balance Sheet still balances. Inheriting the parent's
category at creation keeps the two in agreement. Never overrides a category the user chose.
"""

from __future__ import annotations

import frappe


def inherit_account_category(doc, method=None) -> None:
    if doc.get("account_category") or not doc.get("parent_account"):
        return
    if not frappe.get_meta("Account").has_field("account_category"):
        return
    category = frappe.db.get_value("Account", doc.parent_account, "account_category")
    if category:
        doc.account_category = category
