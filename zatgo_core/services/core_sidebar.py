"""The "ZatGo" Desk sidebar, rebuilt from what this site has switched on.

Apps first, then the general "Settings" group:

- an app with just one destination (ZatGo Space, the switch-only theme / language switcher / VanSaleX web,
  each enabled industry such as ZatGo Restaurant) is a single link, listed first -- a link placed after a
  group would look like one of its items;
- an app with its own workspace AND settings (ZatGo VanSaleX, ZatGo AI, ZatGo Tracker) is a collapsible
  group named after it: "Overview" (its Workspace) plus each of its own settings DocTypes;
- "Settings" holds only the platform's general settings: the App Settings Hub and the shortcuts of
  workspace/zatgo/zatgo.json, minus any app's own settings (those sit in that app's group).

A new sub-app (its `<module>/app_manifest.py`, services/app_catalog.py) or industry shows up here with
nothing else to edit. Apps switched off are left out; their data is untouched. Frappe's sidebar nests one
level only (a Section Break and the `child` links after it), hence a group per app rather than a group of apps.

`sync_core_sidebar()` is an upsert: rows are replaced only when they drift, so it is cheap to call
from migrate and from ZG System Settings' on_update (when a switch is flipped).
"""

from __future__ import annotations

import json
import os

import frappe

from zatgo_core.services import app_catalog

NAME = "ZatGo"
ICON = "setting"
SETTINGS_LABEL = "Settings"
OVERVIEW_LABEL = "Overview"
HUB_PAGE = "zg-app-hub"

# Catalog groups that are apps. "ui" (ZatGo Desk Theme, Language Switcher, VanSaleX Web) has no
# page of its own, only a per-site switch: listed while on, opening the App Settings Hub.
APP_GROUPS = ("app", "bundled", "ui")


def _section(label: str) -> dict:
    return {"type": "Section Break", "label": label, "collapsible": 1, "keep_closed": 0, "indent": 0, "child": 0}


def _link(label: str, link_type: str, link_to: str, icon: str, child: int = 1) -> dict:
    """child=1: inside the Section Break above it; child=0: a link on its own."""
    return {
        "type": "Link",
        "label": label,
        "link_type": link_type,
        "link_to": link_to,
        "icon": icon or "list",
        "child": child,
        "indent": 0,
        "collapsible": 1,
        "keep_closed": 0,
        "show_arrow": 0,
    }


def _is_app_on(app: dict, switches: dict[str, bool]) -> bool:
    if app["group"] not in APP_GROUPS:
        return False
    if app["switch_field"]:
        return bool(switches.get(app["key"]))
    return True


def _entries(app: dict) -> list[tuple[str, str, str, str]]:
    """(label, link_type, link_to, icon) of what an app offers that exists on this site: its Workspace
    ("Overview", the first one of the manifest that exists), then each settings DocType. A switch-only
    app offers the hub, where its switch lives."""
    rows: list[tuple[str, str, str, str]] = []
    for name in app["workspaces"]:
        if frappe.db.exists("Workspace", name):
            rows.append((OVERVIEW_LABEL, "Workspace", name, app["icon"]))
            break
    for doctype, label in app["settings"]:
        if frappe.db.exists("DocType", doctype):
            rows.append((label, "DocType", doctype, "list"))
    if not rows and app["switch_field"] and frappe.db.exists("Page", HUB_PAGE):
        rows.append((app["label"], "Page", HUB_PAGE, app["icon"]))
    return rows


def _owned_settings() -> set[str]:
    """Settings DocTypes that belong to an app: they sit in its group, not in the general Settings group."""
    return {
        doctype
        for app in app_catalog.catalog()
        if app["group"] in APP_GROUPS
        for doctype, _label in app["settings"]
    }


def _app_rows(app: dict) -> list[dict]:
    entries = _entries(app)
    if not entries:
        return []
    if len(entries) == 1:  # one destination: a link under the app's own name
        _label, link_type, link_to, _icon = entries[0]
        return [_link(app["label"], link_type, link_to, app["icon"], child=0)]
    return [_section(app["label"]), *(_link(*entry) for entry in entries)]


def app_rows() -> list[dict]:
    """The single links first (a link right after a group would look like part of it), then a group per
    app that has a workspace and settings."""
    from zatgo_core.industries import gate, registry
    from zatgo_core.services.app_state import switches

    on = switches()
    links: list[dict] = []
    groups: list[dict] = []
    for app in app_catalog.catalog():
        if not _is_app_on(app, on):
            continue
        rows = _app_rows(app)
        (groups if rows and rows[0]["type"] == "Section Break" else links).extend(rows)
    enabled = gate.enabled_keys()
    for key, industry in registry.INDUSTRIES.items():
        if key in enabled and frappe.db.exists("Workspace", industry.workspace):
            links.append(_link(industry.workspace, "Workspace", industry.workspace, industry.icon, child=0))  # "ZatGo Restaurant"
    return links + groups


def settings_links() -> list[dict]:
    """The App Settings Hub, then the shortcuts of workspace/zatgo/zatgo.json (kind-aware: a Page
    shortcut stays a Page link) -- the general settings only; an app's own settings are in its group."""
    owned = _owned_settings()
    path = os.path.join(frappe.get_app_path("zatgo_core"), "zatgo_core", "workspace", "zatgo", "zatgo.json")
    with open(path, encoding="utf-8") as f:
        shortcuts = json.load(f)["shortcuts"]
    links: list[dict] = []
    for s in shortcuts:
        kind, target = s.get("type") or "DocType", s["link_to"]
        if kind == "DocType" and target in owned:
            continue
        if frappe.db.exists(kind, target):
            links.append(_link(s["label"], kind, target, "list"))
    # The hub first, even if the workspace file doesn't list it.
    if not any(row["link_to"] == HUB_PAGE for row in links) and frappe.db.exists("Page", HUB_PAGE):
        links.insert(0, _link("ZatGo Apps", "Page", HUB_PAGE, "setting"))
    return links


def desired_items() -> list[dict]:
    items = app_rows()
    settings = settings_links()
    if settings:
        items += [_section(SETTINGS_LABEL), *settings]
    return items


def _fingerprint(row) -> tuple:
    """What identifies a sidebar row. A Section Break has no link: Frappe fills its link_type with
    "DocType" on save, so only its label counts."""
    get = row.get
    if get("type") == "Section Break":
        return ("Section Break", get("label") or "", int(get("child") or 0))
    return ("Link", get("label") or "", get("link_type") or "", get("link_to") or "", get("icon") or "", int(get("child") or 0))


def _same(rows, wanted: list[dict]) -> bool:
    return len(rows) == len(wanted) and all(_fingerprint(r) == _fingerprint(w) for r, w in zip(rows, wanted))


def sync_core_sidebar() -> bool:
    """Make the "ZatGo" Workspace Sidebar match this site's enabled apps. Returns True if it changed.
    Does nothing until the sidebar exists (ensure_core_desk creates it)."""
    if not frappe.db.exists("Workspace Sidebar", NAME):
        return False
    wanted = desired_items()
    sidebar = frappe.get_doc("Workspace Sidebar", NAME)
    if _same(sidebar.items, wanted):
        return False
    sidebar.set("items", [])
    for item in wanted:
        sidebar.append("items", item)
    sidebar.flags.ignore_links = True
    sidebar.save(ignore_permissions=True)
    return True
