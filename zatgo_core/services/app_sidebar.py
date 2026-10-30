"""The Desk sidebar of each ZatGo app: what opens when an app is clicked in the ZatGo folder of the Apps screen.

Every app (a catalog app of group "app" / "bundled", or an industry) has its own Workspace Sidebar -- the one named
after its Workspace, which Frappe made for it -- so it opens like any ERPNext app (Banking, HR ...): the app's name
and icon on top, Search and Notification, then

- **Overview** -- the app's Workspace,
- **Settings** -- one item per Tab Break of the app's settings DocType(s) (`navigate_to_tab`: the form opens on that
  tab). All configuration of the app's web / mobile / desktop clients lives here, on the backend,
- one group per card of the Workspace (its DocTypes, Reports, Pages),
- the Workspace's shortcuts that no card already lists, under "Shortcuts".

The sidebar is the same for every user: Frappe filters each item by the viewer's permissions when it boots the sidebar
(frappe.boot.get_sidebar_items -> `is_item_allowed`), so a role sees only what it may open. An app that is switched off
keeps its sidebar with no items (Frappe shows a sidebar only when it has an item), so switching back on is one sync.

`sync_app_sidebars()` is an upsert like core_sidebar.sync_core_sidebar(): rows are replaced only when they drift, so
it is cheap to call from migrate and from ZG System Settings' on_update.
"""

from __future__ import annotations

import frappe

from zatgo_core.services import app_page
from zatgo_core.services.core_sidebar import _fingerprint, _link, _same, _section

OVERVIEW_LABEL = "Overview"
SETTINGS_LABEL = "Settings"
SHORTCUTS_LABEL = "Shortcuts"
LINK_TYPES = ("DocType", "Report", "Page")


def sidebar_name(app: dict) -> str:
    """The Workspace Sidebar of an app: named after its Workspace (the first of its manifest that exists), else its label."""
    return next((w for w in app["workspaces"] if frappe.db.exists("Workspace", w)), app["label"])


def _workspace_name(app: dict) -> str | None:
    return next((w for w in app["workspaces"] if frappe.db.exists("Workspace", w)), None)


def settings_sidebars() -> dict[str, str]:
    """Settings DocType -> the sidebar of the (enabled) app it belongs to."""
    return {
        doctype: sidebar_name(app)
        for app in app_page.apps()
        if app_page.is_enabled(app)
        for doctype, _label in app["settings"]
    }


def _settings_links(app: dict) -> list[dict]:
    """One row per Tab Break of each settings DocType (a DocType without tabs: one row named after it)."""
    rows: list[dict] = []
    for doctype, label in app["settings"]:
        if not frappe.db.exists("DocType", doctype):
            continue
        breaks = app_page.tab_breaks(doctype)
        if not breaks:
            rows.append(_link(label, "DocType", doctype, "setting"))
        for tab in breaks:
            row = _link(tab["label"], "DocType", doctype, "setting")
            row["navigate_to_tab"] = tab["key"]
            rows.append(row)
    return rows


def _workspace_groups(name: str, skip: set[str]) -> list[dict]:
    """The Workspace's cards as sections of links, then its uncovered shortcuts as a "Shortcuts" section. `skip`:
    DocTypes already listed under Settings."""
    ws = frappe.get_doc("Workspace", name)
    rows: list[dict] = []
    seen: set[tuple[str, str]] = {("DocType", dt) for dt in skip}
    section_open = False
    for row in ws.links:
        if row.type == "Card Break":
            rows.append(_section(row.label or name))
            section_open = True
        elif row.type == "Link" and section_open and row.link_type in LINK_TYPES and row.link_to and (row.link_type, row.link_to) not in seen:
            rows.append(_link(row.label or row.link_to, row.link_type, row.link_to, "list"))
            seen.add((row.link_type, row.link_to))
    # A card with no link left (the sections above are added blind) must not leave an empty header behind.
    rows = _drop_empty_sections(rows)
    extra = [
        _link(s.label or s.link_to, s.type, s.link_to, "list")
        for s in ws.shortcuts
        if s.type in LINK_TYPES and s.link_to and (s.type, s.link_to) not in seen
    ]
    if extra:
        rows += [_section(SHORTCUTS_LABEL), *extra]
    return rows


def _drop_empty_sections(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        if row["type"] == "Section Break" and (i + 1 == len(rows) or rows[i + 1]["type"] == "Section Break"):
            continue
        out.append(row)
    return out


def desired_items(app: dict) -> list[dict]:
    """Top-level Overview, then the Settings section, then the Workspace's own groups (every row after a Section
    Break is `child=1`, nothing follows the last section at top level -- see core_sidebar's docstring)."""
    items: list[dict] = []
    workspace = _workspace_name(app)
    if workspace:
        items.append(_link(OVERVIEW_LABEL, "Workspace", workspace, app["icon"], child=0))
    settings = _settings_links(app)
    if settings:
        items += [_section(SETTINGS_LABEL), *settings]
    if workspace:
        items += _workspace_groups(workspace, {dt for dt, _ in app["settings"]})
    return items


def _fp(row) -> tuple:
    get = row.get
    return (*_fingerprint(row), get("navigate_to_tab") or "")


def _same_items(rows, wanted: list[dict]) -> bool:
    return len(rows) == len(wanted) and all(_fp(r) == _fp(w) for r, w in zip(rows, wanted))


def _sync_one(app: dict, enabled: bool) -> bool:
    name = sidebar_name(app)
    exists = frappe.db.exists("Workspace Sidebar", name)
    wanted = desired_items(app) if enabled else []
    if not exists:
        if not wanted:
            return False
        doc = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "name": name,
                "title": name,
                "header_icon": app["icon"] or "list",
                "module": "ZatGo Core",
                "app": "zatgo_core",
                "standard": 0,
                "items": wanted,
            }
        )
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        return True
    sidebar = frappe.get_doc("Workspace Sidebar", name)
    if _same_items(sidebar.items, wanted):
        return False
    sidebar.set("items", [])
    for item in wanted:
        sidebar.append("items", item)
    sidebar.flags.ignore_links = True
    sidebar.save(ignore_permissions=True)
    return True


def sync_app_sidebars() -> bool:
    """Make every app's Workspace Sidebar match what this site has switched on. True if any changed (the caller
    clears the Desk cache)."""
    changed = False
    for app in app_page.apps():
        try:
            changed = _sync_one(app, app_page.is_enabled(app)) or changed
        except Exception:
            frappe.log_error(title=f"zatgo_core: sync sidebar of {app['label']}")
    return changed
