"""Rename the `ZG <Name>` DocTypes: the prefix is dropped (the 7 whose plain name already exists in ERPNext / Frappe
become `ZatGo <Name>`); Number Cards, Roles and the Custom HTML Block become `ZatGo <Name>`.

Runs in [pre_model_sync], first in the list: Frappe's model sync would otherwise create the new DocTypes next to the old
ones and leave the data behind. `frappe.rename_doc` renames the table and repoints Link fields, child tables, DocPerms,
Custom Fields and Property Setters. Idempotent: a name already renamed (or never present) is skipped; when both exist the
old one is left alone and reported -- never merged or deleted."""

from __future__ import annotations

DOCTYPES = {
    "ZG Gym Plan": "Gym Plan",
    "ZG Vehicle": "ZatGo Vehicle",
    "ZG Application Registry": "Application Registry",
    "ZG Table": "Table",
    "ZG Metal Rate": "Metal Rate",
    "ZG Number Series Settings": "Number Series Settings",
    "ZG Number Series Item": "Number Series Item",
    "ZG MyBis Settings": "MyBis Settings",
    "ZG Sales Invoice Naming Rule": "Sales Invoice Naming Rule",
    "ZG Van Sale Profile Access": "Van Sale Profile Access",
    "ZG Integration Settings": "Integration Settings",
    "ZG Order": "Order",
    "ZG Edition": "Edition",
    "ZG Licence History": "Licence History",
    "ZG Registered Application": "Registered Application",
    "ZG Delivery Stop": "ZatGo Delivery Stop",
    "ZG Edition Feature": "Edition Feature",
    "ZG Payment Allocation": "Payment Allocation",
    "ZG Company Settings": "Company Settings",
    "ZG Config History": "Config History",
    "ZG User Preferences": "User Preferences",
    "ZG Payment Settings": "Payment Settings",
    "ZG Notification Settings": "ZatGo Notification Settings",
    "ZG Printer Settings": "Printer Settings",
    "ZG Branch Settings": "Branch Settings",
    "ZG Storage Settings": "Storage Settings",
    "ZG POS Settings": "ZatGo POS Settings",
    "ZG Device Token": "Device Token",
    "ZG Service Ticket": "Service Ticket",
    "ZG Van Sale Profile": "Van Sale Profile",
    "ZG Duplicate Override Log": "Duplicate Override Log",
    "ZG Enabled Industry": "Enabled Industry",
    "ZG Client Application": "Client Application",
    "ZG System Settings": "ZatGo System Settings",
    "ZG Gym Membership": "Gym Membership",
    "ZG Feature Flag": "Feature Flag",
    "ZG Setting Section": "Setting Section",
    "ZG Order Item": "Order Item",
    "ZG Theme Settings": "Theme Settings",
    "ZG Language Settings": "Language Settings",
    "ZG Config Profile": "Config Profile",
    "ZG Delivery Boy": "Delivery Boy",
    "ZG Sync Settings": "Sync Settings",
    "ZG Duplicate Role": "Duplicate Role",
    "ZG Licence": "Licence",
    "ZG Mode of Payment Account": "ZatGo Mode of Payment Account",
    "ZG Duplicate Rule": "Duplicate Rule",
    "ZG Duplicate Rule Field": "Duplicate Rule Field",
    "ZG KDS Ticket": "KDS Ticket",
    "ZG Gym Attendance": "Gym Attendance",
    "ZG Audit Log": "Audit Log",
    "ZG Module": "Module",
    "ZG Trip": "Trip",
    "ZG Application Settings": "Application Settings",
    "ZG Sales Invoice Naming Settings": "Sales Invoice Naming Settings",
    "ZG Feature": "Feature",
    "ZG Duplicate Prevention Settings": "Duplicate Prevention Settings",
    "ZG Security Settings": "ZatGo Security Settings",
    "ZG Offline Sale Issue": "Offline Sale Issue"
}

NUMBER_CARDS = ('ZG Purchase Invoices', 'ZG Purchase Invoice Total', 'ZG Sales Orders', 'ZG Sales Invoice Total', 'ZG Sales Order Total', 'ZG Purchase Orders', 'ZG Sales Invoices', 'ZG Purchase Order Total')

BLOCKS = ("ZG ERP Summary",)


def _zatgo(name: str) -> str:
    return "ZatGo " + name[3:]


def _rename(doctype: str, old: str, new: str, report: list) -> None:
    import frappe

    if not frappe.db.exists(doctype, old):
        return
    if frappe.db.exists(doctype, new):
        report.append(f"both exist, left alone: {doctype} {old!r} / {new!r}")
        return
    frappe.rename_doc(doctype, old, new, force=True, merge=False, rebuild_search=False)
    report.append(f"renamed {doctype}: {old} -> {new}")


def execute() -> None:
    import frappe

    frappe.flags.in_patch = True
    report: list[str] = []
    for old, new in DOCTYPES.items():
        _rename("DocType", old, new, report)
    for old in NUMBER_CARDS:
        _rename("Number Card", old, _zatgo(old), report)
    for old in BLOCKS:
        _rename("Custom HTML Block", old, _zatgo(old), report)
    for old in frappe.get_all("Role", filters={"name": ["like", "ZG %"]}, pluck="name"):
        _rename("Role", old, _zatgo(old), report)
    frappe.clear_cache()
    for line in report:
        print(line)
