"""ZG POS Settings -> Pages: a site shows only the POS screen until its pages are ticked.

Sites that already run the Restaurant industry were using Floor, Orders, Kitchen, Billing and the rest, so they would
lose them on this release. Tick every page once for those sites. A site where any page switch was ever stored (the admin
already chose) and every site without the Restaurant industry are left alone: POS only is the default for them."""

import frappe

SETTINGS = "ZG POS Settings"
PAGES = ("dashboard", "orders", "floor", "kds", "catalog", "billing", "delivery", "inventory", "reports")


def execute() -> None:
    if not frappe.db.exists("DocType", SETTINGS):
        return
    fields = [f"page_{p}" for p in PAGES]
    if frappe.db.sql(
        "select 1 from `tabSingles` where doctype = %s and field in %s limit 1", (SETTINGS, tuple(fields))
    ):
        return
    from zatgo_core.industries.gate import is_enabled

    if not is_enabled("restaurant"):
        return
    for field in fields:
        frappe.db.set_single_value(SETTINGS, field, 1)
    frappe.clear_document_cache(SETTINGS, SETTINGS)
