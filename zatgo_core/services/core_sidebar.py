"""The "ZatGo" Desk sidebar, rebuilt from what this site has switched on.

Two groups: "Apps" -- one link per enabled app (VanSaleX, ZatGo AI, Tracker, ZatGo Space, each
enabled industry such as Resto POS) -- and "Settings": the App Settings Hub and the platform's
settings shortcuts (workspace/zatgo/zatgo.json). A new sub-app (its `<module>/app_manifest.py`,
services/app_catalog.py) or industry shows up here with nothing else to edit.

An app opens its own Workspace when it has one (first existing name in the manifest's `workspaces`),
otherwise its first settings DocType. Apps switched off are left out; their data is untouched.

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
APPS_LABEL = "Apps"
SETTINGS_LABEL = "Settings"
HUB_PAGE = "zg-app-hub"

# Catalog groups that are apps. "ui" (ZatGo Desk Theme, Language Switcher, VanSaleX Web) has no
# page of its own, only a per-site switch: listed while on, opening the App Settings Hub.
APP_GROUPS = ("bundled", "ui")
# Core catalog entries that are apps although they have no on/off switch.
ALWAYS_ON_APPS = ("vansalex",)


def _section(label: str) -> dict:
    return {"type": "Section Break", "label": label, "collapsible": 1, "keep_closed": 0, "indent": 0, "child": 0}


def _link(label: str, link_type: str, link_to: str, icon: str) -> dict:
    return {
        "type": "Link",
        "label": label,
        "link_type": link_type,
        "link_to": link_to,
        "icon": icon or "list",
        "child": 1,
        "indent": 0,
        "collapsible": 1,
        "keep_closed": 0,
        "show_arrow": 0,
    }


def _is_app_on(app: dict, switches: dict[str, bool]) -> bool:
    if app["group"] not in APP_GROUPS and app["key"] not in ALWAYS_ON_APPS:
        return False
    if app["switch_field"]:
        return bool(switches.get(app["key"]))
    return True


def _target(app: dict) -> tuple[str, str] | None:
    """(link_type, link_to) for an app: its Workspace if it has one, else its first settings DocType."""
    for name in app["workspaces"]:
        if frappe.db.exists("Workspace", name):
            return "Workspace", name
    for doctype, _label in app["settings"]:
        if frappe.db.exists("DocType", doctype):
            return "DocType", doctype
    if app["switch_field"] and frappe.db.exists("Page", HUB_PAGE):
        return "Page", HUB_PAGE  # a switch-only app: its switch is managed in the hub
    return None


def app_links() -> list[dict]:
    """One Link per enabled app, then per enabled industry."""
    from zatgo_core.industries import gate, registry
    from zatgo_core.services.ui_apps import switches

    on = switches()
    links: list[dict] = []
    for app in app_catalog.catalog():
        if not _is_app_on(app, on):
            continue
        target = _target(app)
        if target:
            links.append(_link(app["label"], target[0], target[1], app["icon"]))
    enabled = gate.enabled_keys()
    for key, industry in registry.INDUSTRIES.items():
        if key in enabled and frappe.db.exists("Workspace", industry.workspace):
            links.append(_link(industry.workspace, "Workspace", industry.workspace, industry.icon))  # "ZatGo Restaurant"
    return links


def settings_links() -> list[dict]:
    """The App Settings Hub, then the shortcuts of workspace/zatgo/zatgo.json (kind-aware: a Page
    shortcut stays a Page link)."""
    path = os.path.join(frappe.get_app_path("zatgo_core"), "zatgo_core", "workspace", "zatgo", "zatgo.json")
    with open(path, encoding="utf-8") as f:
        shortcuts = json.load(f)["shortcuts"]
    links: list[dict] = []
    for s in shortcuts:
        kind, target = s.get("type") or "DocType", s["link_to"]
        if frappe.db.exists(kind, target):
            links.append(_link(s["label"], kind, target, "list"))
    # The hub first, even if the workspace file doesn't list it.
    if not any(row["link_to"] == HUB_PAGE for row in links) and frappe.db.exists("Page", HUB_PAGE):
        links.insert(0, _link("App Settings Hub", "Page", HUB_PAGE, "setting"))
    return links


def desired_items() -> list[dict]:
    items: list[dict] = []
    apps = app_links()
    if apps:
        items += [_section(APPS_LABEL), *apps]
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
