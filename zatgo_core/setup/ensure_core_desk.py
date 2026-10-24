"""The "ZatGo" entry in Desk (App screen + sidebar) on every site: one place
for the platform's apps and settings. Its Workspace is a synced file
(workspace/zatgo/zatgo.json); the Sidebar and Desktop Icon are made here because
install purges every Desktop Icon of this app (install.purge_desk_ui_leftovers)
before this runs. The sidebar's items -- the "Apps" section (the enabled apps), then
"General Settings" -- come from services/core_sidebar.py and are re-synced on every
migrate and when an app is switched on or off; the apps' own rail icons are kept
hidden (services/app_desk.py)."""

from __future__ import annotations

import os

import frappe

from zatgo_core.services import app_desk, core_sidebar

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
# normally deletes the old Workspace record; this makes sure of it where the purge didn't run, and gives
# the rail entry that goes with it (Workspace Sidebar + Desktop Icon, made when the workspace was first
# created, named after it) the new name too.
LEGACY_WORKSPACES = {"ZatGo VanSaleX": ("VanSaleX",)}


def _retire_legacy_workspaces() -> None:
    for new, legacy in LEGACY_WORKSPACES.items():
        if not frappe.db.exists("Workspace", new):
            continue  # never retire the only one
        for old in legacy:
            # Rows pointing at the old workspace follow the rename whether or not the record is still there
            # (migrate's orphan purge may have deleted it first).
            frappe.db.sql(
                "update `tabWorkspace Sidebar Item` set link_to = %s where link_type = 'Workspace' and link_to = %s",
                (new, old),
            )
            if frappe.db.exists("Workspace", old):
                try:
                    frappe.delete_doc("Workspace", old, force=1, ignore_permissions=True)
                except Exception:
                    frappe.log_error(title=f"zatgo_core: retire legacy workspace {old}")
        _adopt_legacy_rail_entry(new, legacy)


def _adopt_legacy_rail_entry(new: str, legacy: tuple[str, ...]) -> None:
    """The rail icon + sidebar named after a retired workspace become [new]: renamed where [new] does not
    exist yet (their items and links follow), deleted where it does. Frappe v16 shows an icon only when its
    label equals its sidebar's name, so both get the new name."""
    for old in legacy:
        try:
            if frappe.db.exists("Workspace Sidebar", old):
                if frappe.db.exists("Workspace Sidebar", new):
                    frappe.delete_doc("Workspace Sidebar", old, force=1, ignore_permissions=True)
                else:
                    frappe.rename_doc("Workspace Sidebar", old, new, force=True, show_alert=False)
                    frappe.db.set_value("Workspace Sidebar", new, "title", new, update_modified=False)
            if frappe.db.exists("Desktop Icon", old):
                if frappe.db.exists("Desktop Icon", new):
                    frappe.delete_doc("Desktop Icon", old, force=1, ignore_permissions=True)
                elif frappe.db.exists("Workspace Sidebar", new):  # else: nothing to point a renamed icon at
                    frappe.rename_doc("Desktop Icon", old, new, force=True, show_alert=False)
                    frappe.db.set_value("Desktop Icon", new, {"label": new, "link_to": new}, update_modified=False)
        except Exception:
            frappe.log_error(title=f"zatgo_core: adopt legacy rail entry {old} -> {new}")


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
                "icon_type": "Folder",
                "icon": ICON,
                "standard": 0,
                "hidden": 0,
            }
        )
        icon.flags.ignore_links = True
        icon.insert(ignore_permissions=True)
    # ZatGo is a folder on the Apps screen: its popup lists the apps and General Settings (events/boot.py).
    if frappe.db.get_value("Desktop Icon", NAME, "icon_type") != "Folder":
        frappe.db.set_value(
            "Desktop Icon", NAME, {"icon_type": "Folder", "link_type": "", "link_to": ""}, update_modified=False
        )
    # An existing sidebar is brought up to date too (it used to be frozen at first creation).
    core_sidebar.sync_core_sidebar()
    # Apps open from ZatGo > Apps: their own rail icons (created by their install / industries sync, which
    # ran before this) stay hidden.
    app_desk.sync_rail_icons()
