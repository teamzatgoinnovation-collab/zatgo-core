"""Desk entries of the apps listed in the ZatGo sidebar's "Apps" section.

Two things live here:

- An app that lives inside the core module (group "app", e.g. VanSaleX) has a Workspace that is a synced file --
  present on every site -- so a switched-off app is *hidden*, not deleted: its Workspace gets the hidden flag,
  cleared again when it is switched on. Nothing is removed, so switching on needs no re-import, and a migrate that
  re-syncs the Workspace file is followed by `sync_app_desk` (ensure_ui_apps), which sets the flag back.
  (Bundled modules keep their Desk records outside the synced folders instead, services/bundled_apps.py.)
- The rail icons of every app and industry (ZatGo AI, ZatGo VanSaleX, ZatGo Gym ...) are always hidden: apps open
  from ZatGo > Apps, not from a rail icon of their own. Only the Desktop Icon is hidden -- never the Workspace
  (the Apps entry links to it) and never the Workspace Sidebar -- so showing an icon again is one flag.
"""

from __future__ import annotations

import frappe

from zatgo_core.services import app_catalog, app_state


def _set_hidden(app: dict, hidden: int) -> bool:
    """Set the hidden flag of the app's Workspace(s); True if any row changed."""
    changed = False
    for name in app["workspaces"]:
        if frappe.db.exists("Workspace", name) and frappe.db.get_value("Workspace", name, "is_hidden") != hidden:
            frappe.db.set_value("Workspace", name, "is_hidden", hidden, update_modified=False)
            changed = True
    return changed


def rail_icon_targets() -> list[str]:
    """Workspace / Workspace Sidebar names of every app and industry, current and legacy: what their rail
    Desktop Icons link to."""
    from zatgo_core.services import app_page

    names: list[str] = []
    for app in app_page.apps():
        names.extend(app["workspaces"])
    return names


def sync_rail_icons() -> bool:
    """Hide the rail icon of every app and industry (the ZatGo icon itself is never touched).
    True if any row changed (the caller clears the Desk cache)."""
    names = rail_icon_targets()
    if not names:
        return False
    changed = False
    for icon in frappe.get_all("Desktop Icon", filters={"link_to": ["in", names]}, fields=["name", "hidden"]):
        if not int(icon.hidden or 0):
            frappe.db.set_value("Desktop Icon", icon.name, "hidden", 1, update_modified=False)
            changed = True
    return changed


def sync_app_desk() -> bool:
    """Hide the Workspaces of every switched-off in-core app, show those of the switched-on ones, and keep
    every app's rail icon hidden. Returns True if anything changed (the caller clears the Desk cache)."""
    on = app_state.switches()
    changed = False
    for app in app_catalog.catalog():
        if app["group"] not in ("app", "ui") or not app["switch_field"] or not app["workspaces"]:
            continue
        changed = _set_hidden(app, 0 if on.get(app["key"]) else 1) or changed
    return sync_rail_icons() or changed
