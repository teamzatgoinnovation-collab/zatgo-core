"""The apps behind the ZatGo folder of the Apps screen, and how Desk URLs map to them.

An app is what the folder lists: a catalog app of group "app" / "bundled" / "ui" (VanSaleX, POS, ZatGo AI, Tracker,
Space, MyBis, Desk Theme, Language Switcher, VanSaleX Web) or an industry (Restaurant, Gym ...). This module knows the list (`apps()`), whether one is on, what is wrong with its
setup (`warnings`), the Tab Breaks of its settings forms (`tab_breaks`, the Settings items of its sidebar,
services/app_sidebar.py) and the old Desk URLs that now open its Workspace (`old_url_redirects`).
"""

from __future__ import annotations

import re
from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.services import app_catalog, app_state
from zatgo_core.services.core_sidebar import APP_GROUPS


def route_key(app: dict[str, Any]) -> str:
    """The app's old page segment: the slug of its label (`ZatGo VanSaleX` -> `zatgo-vansalex`)."""
    return re.sub(r"[^a-z0-9]+", "-", (app["label"] or "").lower()).strip("-")


def apps() -> list[dict[str, Any]]:
    """Every app that can have a page, enabled or not: catalog apps first, then industries. Each row:
    key, label, icon, kind ("app" / "industry"), workspaces (names, Overview source first), settings
    [(DocType, label), ...], description, version."""
    from zatgo_core.industries import registry

    rows: list[dict[str, Any]] = []
    for app in app_catalog.catalog():
        if app["group"] in APP_GROUPS:
            rows.append({**app, "kind": "app", "workspaces": tuple(app["workspaces"]), "settings": tuple(app["settings"]), "route_key": route_key(app)})
    for key, industry in registry.INDUSTRIES.items():
        if not industry.implemented:  # "coming soon" entries have no Workspace and cannot be switched on
            continue
        rows.append(
            {
                "key": key,
                "label": industry.workspace,
                "icon": industry.icon,
                "kind": "industry",
                "group": "industries",
                "description": industry.description,
                "workspaces": (industry.workspace,),
                "settings": (),
                "version": __version__,
                "switch_field": "",
                "route_key": route_key({"label": industry.workspace}),
            }
        )
    return rows


def find(segment: str) -> dict[str, Any] | None:
    """The app behind a URL segment (its route key; the bare key works too), or None."""
    seg = (segment or "").strip().lower()
    rows = apps()
    for app in rows:
        if app["route_key"] == seg:
            return app
    key = seg.replace("-", "_")
    return next((app for app in rows if app["key"] == key), None)


def workspace_slug(name: str) -> str:
    """The Desk URL segment of a Workspace (`frappe.router.slug`): `ZatGo VanSaleX` -> `zatgo-vansalex`."""
    return frappe.scrub(name).replace("_", "-")


def old_url_redirects() -> dict[str, str]:
    """Old Desk sub-path -> the app's Workspace (`frappe.re_route`): the names before the apps were renamed
    "ZatGo ...", and `zg-app/<route key>`, the tabbed page this sidebar replaced."""
    out: dict[str, str] = {}
    for app in apps():
        current = next((w for w in app["workspaces"] if frappe.db.exists("Workspace", w)), None)
        if not current:
            continue
        target = workspace_slug(current)
        for name in app["workspaces"]:
            if workspace_slug(name) != target:
                out[workspace_slug(name)] = target
        out[f"zg-app/{app['route_key']}"] = target
    return out


# -- page content -----------------------------------------------------------------------------------------------


def is_enabled(app: dict[str, Any]) -> bool:
    if app["kind"] == "industry":
        from zatgo_core.industries import gate

        return app["key"] in gate.enabled_keys()
    return app_state.is_on(app["key"]) if app["switch_field"] else True


def warnings(app: dict[str, Any], on: dict[str, bool], enabled: bool) -> list[str]:
    """Why an app that is on is not (fully) set up -- only conditions that can be checked cheaply and
    that are certainly wrong. Nothing is reported for an app that is off."""
    if not enabled:
        return []
    out: list[str] = []
    for need in app.get("requires", ()):
        other = app_catalog.get(need)
        if other and other["switch_field"] and not on.get(need):
            out.append(f"Needs {other['label']}, which is off")
    for dt, label in app["settings"]:
        if not frappe.db.exists("DocType", dt):
            out.append(f"{label} is missing: run bench migrate")
    if app.get("group") == "bundled" and app.get("module_def") and not frappe.db.exists("Module Def", app["module_def"]):
        out.append(f"Module {app['module_def']} is missing: run bench migrate")
    if app["workspaces"] and not any(frappe.db.exists("Workspace", w) for w in app["workspaces"]):
        out.append("Desk workspace is not set up yet: save the switch again or run bench migrate")
    return out


def tab_breaks(doctype: str) -> list[dict[str, str]]:
    """The tabs of a settings form, in order: [{key (fieldname), label}]."""
    return [
        {"key": f.fieldname, "label": f.label or f.fieldname}
        for f in frappe.get_meta(doctype).fields
        if f.fieldtype == "Tab Break" and not f.hidden
    ]
