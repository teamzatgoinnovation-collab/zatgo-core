"""The "ZatGo" Desk sidebar, rebuilt from what this site has switched on.

Only **General Settings** -- the platform's settings. The apps are not here: each has its own sidebar
(services/app_sidebar.py) and is opened from the ZatGo folder of the Apps screen (`events/boot.py`). General Settings:
the App Settings Hub first (where every app is switched on or off), then the shortcuts of workspace/zatgo/zatgo.json
(minus any app's own settings, which are in that app's sidebar).

A new sub-app (its `<module>/app_manifest.py`, services/app_catalog.py) or industry shows up here with nothing
else to edit. Apps switched off are left out; their data is untouched. Frappe's sidebar nests one level only:
a Section Break and the `child` links after it, so every row after a section is `child=1` and nothing may follow
the last section at top level (it would look like one of its items).

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
GENERAL_LABEL = "General Settings"
HUB_PAGE = "zg-app-hub"
HUB_LABEL = "Apps (on / off)"

# Catalog groups that are apps: each opens in the ZatGo popup while it is on, with its own sidebar. "ui" (Desk Theme,
# Language Switcher, VanSaleX Web) are apps too; only their on/off switch lives in General Settings (the hub).
APP_GROUPS = ("app", "bundled", "ui")


def _section(label: str) -> dict:
    return {"type": "Section Break", "label": label, "collapsible": 1, "keep_closed": 0, "indent": 0, "child": 0}


def _link(label: str, link_type: str, link_to: str, icon: str, child: int = 1) -> dict:
    """child=1: inside the Section Break above it (every row of the two sections)."""
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


def _owned_settings() -> set[str]:
    """Settings DocTypes that belong to an app: they are tabs of its page, not General Settings entries."""
    return {
        doctype
        for app in app_catalog.catalog()
        if app["group"] in APP_GROUPS
        for doctype, _label in app["settings"]
    }


def general_links() -> list[dict]:
    """The App Settings Hub, the shortcuts of workspace/zatgo/zatgo.json (kind-aware: a Page shortcut stays a
    Page link) minus any app's own settings. The hub comes first: it is where an app is switched on or off."""
    from zatgo_core.services.app_state import switches

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
    hub = [row for row in links if row["link_to"] == HUB_PAGE]
    if not hub and frappe.db.exists("Page", HUB_PAGE):  # even if the workspace file doesn't list it
        hub = [_link(HUB_LABEL, "Page", HUB_PAGE, "setting")]
    rest = [row for row in links if row["link_to"] != HUB_PAGE]
    return hub + rest


def desired_items() -> list[dict]:
    items: list[dict] = []
    general = general_links()
    if general:
        items += [_section(GENERAL_LABEL), *general]
    return items


def _fingerprint(row) -> tuple:
    """What identifies a sidebar row. A Section Break has no link: Frappe fills its link_type with
    "DocType" on save, so only its label counts. The flags are part of it: a row whose only difference
    is how it renders must still be seen as drift."""
    get = row.get
    flags = tuple(int(get(k) or 0) for k in ("child", "indent", "collapsible", "keep_closed", "show_arrow"))
    if get("type") == "Section Break":
        return ("Section Break", get("label") or "", *flags)
    return (
        "Link",
        get("label") or "",
        get("link_type") or "",
        get("link_to") or "",
        get("icon") or "",
        get("route_options") or "",
        *flags,
    )


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
