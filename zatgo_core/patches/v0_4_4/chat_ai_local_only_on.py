"""ZatGo AI is local-only: tick 'Local models only' on sites that never had the field.

The protection already counts a missing value as ON (chat_ai/erpnext/settings.py), but the form
would show the box unticked. Writing the value makes the form say what is enforced. A site that
explicitly saved it as 0 (an administrator allowed an external API) is left alone."""

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "Chat AI Settings"):
        return
    if frappe.db.sql("select 1 from `tabSingles` where doctype = %s and field = %s", ("Chat AI Settings", "local_only")):
        return
    frappe.db.set_single_value("Chat AI Settings", "local_only", 1)
    frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")
