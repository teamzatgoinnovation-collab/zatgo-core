"""Duplicate Prevention is ON unless switched off (manifest `default_on`). Store the 1 so the System Settings form
shows what is enforced; a site that explicitly saved 0 is left alone. Same reasoning as v0_4_9."""

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG System Settings"):
        return
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype = %s and field = %s",
        ("ZG System Settings", "enable_duplicate_prevention"),
    ):
        return
    frappe.db.set_single_value("ZG System Settings", "enable_duplicate_prevention", 1)
    frappe.clear_document_cache("ZG System Settings", "ZG System Settings")
