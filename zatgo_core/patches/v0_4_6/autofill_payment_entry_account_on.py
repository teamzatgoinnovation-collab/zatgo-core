"""Payment Entry account auto-fill: tick 'Auto-fill Account Paid To / Paid From on Payment Entry' on sites that
never had the field.

The code already counts a missing value as ON (services/payment_entry_accounts.autofill_enabled), but a setting
added after ZG System Settings was first saved opens unticked in the form -- and saving the form for any other
reason would then silently switch it off. Writing the value makes the form say what is enforced. A site that
explicitly saved it as 0 is left alone."""

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG System Settings"):
        return
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype = %s and field = %s",
        ("ZG System Settings", "autofill_payment_entry_account"),
    ):
        return
    frappe.db.set_single_value("ZG System Settings", "autofill_payment_entry_account", 1)
    frappe.clear_document_cache("ZG System Settings", "ZG System Settings")
