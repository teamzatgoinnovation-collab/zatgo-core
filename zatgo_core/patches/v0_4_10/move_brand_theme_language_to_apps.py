"""Brand name, logo and theme moved from ZG System Settings to ZG Theme Settings, the default language to ZG Language
Settings (services/ui_settings.py). Copy what a site had stored; a value the new settings already hold is kept, and
the old fields stay where they were (hidden), so a rollback loses nothing."""

import frappe

LEGACY = "ZG System Settings"
MOVES = {
    "ZG Theme Settings": ("brand_name", "company_logo", "theme"),
    "ZG Language Settings": ("language",),
}


def _stored(doctype: str, field: str):
    rows = frappe.db.sql("select value from `tabSingles` where doctype = %s and field = %s", (doctype, field))
    return rows[0][0] if rows and rows[0][0] not in (None, "") else None


def execute() -> None:
    if not frappe.db.exists("DocType", LEGACY):
        return
    for doctype, fields in MOVES.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for field in fields:
            value = _stored(LEGACY, field)
            if value is not None and _stored(doctype, field) is None:
                frappe.db.set_single_value(doctype, field, value)
        frappe.clear_document_cache(doctype, doctype)
