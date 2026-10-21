"""The "ZatGo" entry in Desk (App screen + sidebar) on every site: one place
for the platform's apps and settings. Its Workspace is a synced file
(workspace/zatgo/zatgo.json); the Sidebar and Desktop Icon are made here because
install purges every Desktop Icon of this app (install.purge_desk_ui_leftovers)
before this runs. The sidebar's items -- the enabled apps, then the settings --
come from services/core_sidebar.py and are re-synced on every migrate and when an
app is switched on or off."""

from __future__ import annotations

import os

import frappe

from zatgo_core.services import core_sidebar

NAME = "ZatGo"
ICON = "setting"


def _ensure_workspace() -> None:
    """Fresh install: Frappe imports workspace/zatgo/zatgo.json before
    after_install creates the ZG roles it lists, so that import fails
    silently -- import it again here, where the roles exist."""
    if frappe.db.exists("Workspace", NAME):
        return
    from frappe.modules.import_file import import_file_by_path

    path = os.path.join(frappe.get_app_path("zatgo_core"), "zatgo_core", "workspace", "zatgo", "zatgo.json")
    import_file_by_path(path, force=True)


# The VanSaleX workspace is "ZatGo VanSaleX" now (its synced file was renamed). Migrate's orphan purge
# normally deletes the old record; this makes sure of it where the purge didn't run.
LEGACY_WORKSPACES = {"ZatGo VanSaleX": ("VanSaleX",)}


def _retire_legacy_workspaces() -> None:
    for new, legacy in LEGACY_WORKSPACES.items():
        if not frappe.db.exists("Workspace", new):
            continue
        for old in legacy:
            if frappe.db.exists("Workspace", old):
                frappe.db.sql(
                    "update `tabWorkspace Sidebar Item` set link_to = %s where link_type = 'Workspace' and link_to = %s",
                    (new, old),
                )
                try:
                    frappe.delete_doc("Workspace", old, force=1, ignore_permissions=True)
                except Exception:
                    frappe.log_error(title=f"zatgo_core: retire legacy workspace {old}")


def ensure_core_desk() -> None:
    _retire_legacy_workspaces()
    _ensure_workspace()
    if not frappe.db.exists("Workspace", NAME):
        return  # nothing to point at
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
                "items": core_sidebar.desired_items(),
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
    # An existing sidebar is brought up to date too (it used to be frozen at first creation).
    core_sidebar.sync_core_sidebar()
