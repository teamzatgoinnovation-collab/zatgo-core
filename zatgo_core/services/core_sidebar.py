"""The "ZatGo" Desk sidebar, rebuilt from what this site has switched on.

Two sections:

- **Apps** -- one entry per enabled app: ZatGo VanSaleX, ZatGo AI, ZatGo Tracker, ZatGo Space and each enabled
  industry (ZatGo Restaurant ...). An entry links to the app's Workspace, so what a user sees is exactly what the
  Workspace's own roles allow; `events/boot.py` then points the link at the app's tabbed page
  (`/desk/zg-app/<app>`, services/app_page.py). An app without a Workspace falls back to its first settings DocType.
- **General Settings** -- the platform's settings: the switch-only apps (Desk theme, language switcher, VanSaleX
  web), which open the App Settings Hub where their switch lives, then the hub itself (after them: Frappe highlights
  the last item whose path matches the open page), then the shortcuts of workspace/zatgo/zatgo.json (minus any
  app's own settings, which are tabs of that app's page).

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
APPS_LABEL = "Apps"
GENERAL_LABEL = "General Settings"
HUB_PAGE = "zg-app-hub"
HUB_LABEL = "ZatGo Apps"

# Catalog groups that are apps (an entry under "Apps"). "ui" (ZatGo Desk Theme, Language Switcher, VanSaleX Web)
# has no page of its own, only a per-site switch: listed under General Settings while on, opening the hub.
APP_GROUPS = ("app", "bundled")
SWITCH_GROUPS = ("ui",)


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


def _is_on(app: dict, switches: dict[str, bool]) -> bool:
    if app["switch_field"]:
        return bool(switches.get(app["key"]))
    return True


def landing(app: dict) -> tuple[str, str] | None:
    """(link_type, link_to) an app's entry opens: its Workspace (the first of the manifest that exists), else
    its first settings DocType that exists on this site, else nothing."""
    for name in app["workspaces"]:
        if frappe.db.exists("Workspace", name):
            return "Workspace", name
    for doctype, _label in app["settings"]:
        if frappe.db.exists("DocType", doctype):
            return "DocType", doctype
    return None


def _owned_settings() -> set[str]:
    """Settings DocTypes that belong to an app: they are tabs of its page, not General Settings entries."""
    return {
        doctype
        for app in app_catalog.catalog()
        if app["group"] in APP_GROUPS
        for doctype, _label in app["settings"]
    }


def app_links() -> list[dict]:
    """The enabled apps, then the enabled industries -- all `child=1` rows of the "Apps" section."""
    from zatgo_core.industries import gate, registry
    from zatgo_core.services.app_state import switches

    on = switches()
    links: list[dict] = []
    for app in app_catalog.catalog():
        if app["group"] not in APP_GROUPS or not _is_on(app, on):
            continue
        target = landing(app)
        if target:
            links.append(_link(app["label"], target[0], target[1], app["icon"]))
    enabled = gate.enabled_keys()
    for key, industry in registry.INDUSTRIES.items():
        if key in enabled and frappe.db.exists("Workspace", industry.workspace):
            links.append(_link(industry.workspace, "Workspace", industry.workspace, industry.icon))  # "ZatGo Restaurant"
    return links


def general_links() -> list[dict]:
    """The App Settings Hub, the shortcuts of workspace/zatgo/zatgo.json (kind-aware: a Page shortcut stays a
    Page link) minus any app's own settings, then the switch-only apps that are on."""
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
    # The switch-only apps open the hub too. Frappe highlights the LAST sidebar item whose path matches the
    # open page, so the hub entry must come after them or the hub would show "ZatGo Desk Theme" as active.
    switch_only: list[dict] = []
    if hub:
        on = switches()
        switch_only = [
            _link(app["label"], "Page", HUB_PAGE, app["icon"])
            for app in app_catalog.catalog()
            if app["group"] in SWITCH_GROUPS and _is_on(app, on)
        ]
    return switch_only + hub + rest


def desired_items() -> list[dict]:
    items: list[dict] = []
    apps = app_links()
    if apps:
        items += [_section(APPS_LABEL), *apps]
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
