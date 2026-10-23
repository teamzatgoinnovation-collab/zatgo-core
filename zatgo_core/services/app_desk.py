"""Desk entries of an app that lives inside the core module (group "app", e.g. VanSaleX).

Its Workspace is a synced file of the core module -- present on every site -- so a switched-off app is
*hidden*, not deleted: the Workspace and its rail Desktop Icon get their hidden flag set, and cleared again
when it is switched on. Nothing is removed, so switching on needs no re-import, and a migrate that re-syncs
the Workspace file is followed by `sync_app_desk` (ensure_ui_apps), which sets the flags back. (Bundled
modules keep their Desk records outside the synced folders instead, services/bundled_apps.py.)
"""

from __future__ import annotations

import frappe

from zatgo_core.services import app_catalog, app_state


def _set_hidden(app: dict, hidden: int) -> bool:
    """Set the hidden flags of the app's Workspace(s) and rail icon(s); True if any row changed."""
    names = list(app["workspaces"])
    if not names:
        return False
    changed = False
    for name in names:
        if frappe.db.exists("Workspace", name) and frappe.db.get_value("Workspace", name, "is_hidden") != hidden:
            frappe.db.set_value("Workspace", name, "is_hidden", hidden, update_modified=False)
            changed = True
    for icon in frappe.get_all("Desktop Icon", filters={"link_to": ["in", names]}, fields=["name", "hidden"]):
        if int(icon.hidden or 0) != hidden:
            frappe.db.set_value("Desktop Icon", icon.name, "hidden", hidden, update_modified=False)
            changed = True
    return changed


def sync_app_desk() -> bool:
    """Hide the Desk entries of every switched-off in-core app, show those of the switched-on ones.
    Returns True if anything changed (the caller clears the Desk cache)."""
    on = app_state.switches()
    changed = False
    for app in app_catalog.catalog():
        if app["group"] != "app" or not app["switch_field"]:
            continue
        changed = _set_hidden(app, 0 if on.get(app["key"]) else 1) or changed
    return changed
