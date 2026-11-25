"""ZatGo POS got an app-level switch ('Enable ZatGo POS') that is ON unless switched off.

The app already counts a missing value as ON (services/app_state.py: `default_on`), so no site loses it
before this runs -- but a setting added after ZatGo System Settings was first saved opens unticked in the
form, and saving the form for any other reason would then silently switch POS off. Writing the 1 makes
the form say what is enforced. A site that explicitly saved it as 0 is left alone."""

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "ZatGo System Settings"):
        return
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype = %s and field = %s",
        ("ZatGo System Settings", "enable_zatgo_pos"),
    ):
        return
    frappe.db.set_single_value("ZatGo System Settings", "enable_zatgo_pos", 1)
    frappe.clear_document_cache("ZatGo System Settings", "ZatGo System Settings")
