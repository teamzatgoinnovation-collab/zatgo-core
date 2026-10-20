"""Give accounts without an Account Category the one their parent has.

Companion of events/account_category.py for accounts created before it. Walks the tree top-down
(lft order) so a category propagates through several levels; accounts that already have one, and
accounts under an uncategorised parent, are left alone. Classification only: no GL or stock entry
is touched.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.get_meta("Account").has_field("account_category"):
        return
    rows = frappe.db.sql(
        "select name, parent_account, account_category from `tabAccount` order by company, lft",
        as_dict=True,
    )
    category = {r.name: r.account_category for r in rows}
    updated = 0
    for r in rows:
        if r.account_category or not r.parent_account:
            continue
        inherited = category.get(r.parent_account)
        if not inherited:
            continue
        frappe.db.set_value("Account", r.name, "account_category", inherited, update_modified=False)
        category[r.name] = inherited
        updated += 1
    frappe.db.commit()
    if updated:
        frappe.logger("zatgo_core").info("Account Category inherited on %s accounts", updated)
