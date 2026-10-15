"""The "ZatGo" entry in Desk (App screen + sidebar) on every site: one place
for the platform's settings (system settings and industries, VanSaleX, company,
security, ...). Its Workspace is a synced file (workspace/zatgo/zatgo.json);
the Sidebar and Desktop Icon are made here because install purges every
Desktop Icon of this app (install.purge_desk_ui_leftovers) before this runs."""

from __future__ import annotations

import json
import os

import frappe

NAME = "ZatGo"
ICON = "setting"


def _items() -> list[dict]:
    path = os.path.join(frappe.get_app_path("zatgo_core"), "zatgo_core", "workspace", "zatgo", "zatgo.json")
    with open(path, encoding="utf-8") as f:
        shortcuts = json.load(f)["shortcuts"]
    return [
        {"label": s["label"], "link_type": "DocType", "link_to": s["link_to"], "type": "Link", "icon": "list"}
        for s in shortcuts
        if frappe.db.exists("DocType", s["link_to"])
    ]


def ensure_core_desk() -> None:
    if not frappe.db.exists("Workspace", NAME):
        return  # the synced Workspace is not there (yet): nothing to point at
    if not frappe.db.exists("Workspace Sidebar", NAME):
        sb = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "name": NAME,
                "title": NAME,
                "header_icon": ICON,
                "module": "ZatGo Core",
                "app": "zatgo_core",
                "standard": 0,
                "items": _items(),
            }
        )
        sb.flags.ignore_links = True
        sb.insert(ignore_permissions=True)
    if not frappe.db.exists("Desktop Icon", NAME):
        icon = frappe.get_doc(
            {
                "doctype": "Desktop Icon",
                "label": NAME,
                "app": "zatgo_core",
                "icon_type": "Link",
                "link_type": "Workspace Sidebar",
                "link_to": NAME,
                "icon": ICON,
                "standard": 0,
                "hidden": 0,
            }
        )
        icon.flags.ignore_links = True
        icon.insert(ignore_permissions=True)
