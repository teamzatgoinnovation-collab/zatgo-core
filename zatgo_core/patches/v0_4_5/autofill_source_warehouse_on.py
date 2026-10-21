"""Source Warehouse auto-fill: tick 'Auto-fill Source Warehouse on Documents' on sites that never had the field.

The fill already counts a missing value as ON (events/default_source_warehouse.autofill_enabled), but a
setting added after ZG System Settings was first saved opens unticked in the form -- and saving the form
for any other reason would then silently switch the fill off. Writing the value makes the form say what is
enforced. A site that explicitly saved it as 0 is left alone."""

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG System Settings"):
        return
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype = %s and field = %s",
        ("ZG System Settings", "autofill_source_warehouse"),
    ):
        return
    frappe.db.set_single_value("ZG System Settings", "autofill_source_warehouse", 1)
    frappe.clear_document_cache("ZG System Settings", "ZG System Settings")
