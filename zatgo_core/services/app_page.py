"""The page behind each entry of the ZatGo sidebar's "Apps" section: `/desk/zg-app/<app>[/<tab>]`.

An app is what services/core_sidebar.py lists under "Apps": a catalog app of group "app" / "bundled"
(VanSaleX, ZatGo AI, Tracker, Space) or an industry (Restaurant, Gym ...). This module knows how they map to
URLs and builds the page's content; the page itself is `page/zg_app` and its data comes from
`api/v1/app_page.py`.

Tabs: "Overview" (shortcuts and cards of the app's Workspace, each link filtered the way the Workspace itself
filters it) followed by one tab per Tab Break of the app's settings DocType -- read from the DocType, so a new
Tab Break appears with no other edit. A settings tab opens that DocType's form on that tab (Frappe has no
tab bar for a custom page and a settings form cannot be embedded in one, so both screens draw the same bar).
"""

from __future__ import annotations

import re
from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.services import app_catalog, app_state
from zatgo_core.services.core_sidebar import APP_GROUPS

PAGE = "zg-app"
OVERVIEW = "overview"


class AppPageError(Exception):
    """Why a page cannot be shown: `code` is one of not_found / app_off / forbidden."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def route_key(app: dict[str, Any]) -> str:
    """The app's segment in its URL: the slug of its label (`ZatGo VanSaleX` -> `zatgo-vansalex`).

    Not the bare key (`tracker`): for a two-part route Frappe opens a sidebar whose lower-cased name equals the
    second part, and an auto-generated module sidebar called "Tracker" would win over ZatGo's. Sidebar names
    have spaces, these have hyphens, so they can never be equal."""
    return re.sub(r"[^a-z0-9]+", "-", (app["label"] or "").lower()).strip("-")


def route_for(app: dict[str, Any]) -> str:
    return f"/desk/{PAGE}/{app['route_key']}"


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


def workspace_routes() -> dict[str, str]:
    """Workspace name -> the app's page URL, for every name an app's Workspace has had."""
    routes: dict[str, str] = {}
    for app in apps():
        for name in app["workspaces"]:
            routes[name] = route_for(app)
    return routes


def settings_routes() -> dict[str, str]:
    """Settings DocType -> the page of the app it belongs to (the form shows an "Overview" tab back to it)."""
    routes: dict[str, str] = {}
    for app in apps():
        for doctype, _label in app["settings"]:
            routes[doctype] = app["route_key"]
    return routes


def old_url_redirects() -> dict[str, str]:
    """`frappe.router.slug` of an app's Workspace name -> `zg-app/<app>` : the Desk URLs people have bookmarked."""
    out: dict[str, str] = {}
    for name, route in workspace_routes().items():
        out[frappe.scrub(name).replace("_", "-")] = route.removeprefix("/desk/")
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


def settings_tabs(app: dict[str, Any]) -> list[dict[str, Any]]:
    """One tab per Tab Break of each settings DocType the user can read; a settings DocType without Tab Breaks
    is one tab named after it. Each tab: key, label, kind "settings", doctype, tab (the form tab to open or "")."""
    out: list[dict[str, Any]] = []
    for doctype, label in app["settings"]:
        if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
            continue
        breaks = tab_breaks(doctype)
        if not breaks:
            out.append({"key": frappe.scrub(doctype), "label": label, "kind": "settings", "doctype": doctype, "tab": ""})
        for tab in breaks:
            out.append(
                {"key": tab["key"], "label": tab["label"], "kind": "settings", "doctype": doctype, "tab": tab["key"]}
            )
    return out


def _desk_workspace(name: str):
    """Frappe's own helper for "may this user see this Workspace and each thing on it" (the Workspace page
    uses it); raises frappe.PermissionError for a blocked module."""
    from frappe.desk.desktop import Workspace

    return Workspace({"name": name, "title": name, "public": 1}, True)


def _exists(link_type: str, name: str) -> bool:
    return bool(name) and frappe.db.exists(link_type, name)


def overview(app: dict[str, Any]) -> dict[str, Any] | None:
    """The shortcuts and cards of the app's Workspace that this user may open, or None when the app has no
    Workspace (or the user may not see it)."""
    name = next((w for w in app["workspaces"] if frappe.db.exists("Workspace", w)), None)
    if not name:
        return None
    try:
        ws = _desk_workspace(name)
        if not ws.is_permitted():
            return None
    except frappe.PermissionError:
        return None
    doc = ws.doc

    def allowed(link_type: str, target: str) -> bool:
        if link_type not in ("DocType", "Report", "Page") or not _exists(link_type, target):
            return False
        try:
            return bool(ws.is_item_allowed(target, link_type))
        except Exception:
            return False

    shortcuts = [
        {
            "label": s.label or s.link_to,
            "type": s.type,
            "name": s.link_to,
            "doc_view": s.doc_view or "",
        }
        for s in doc.shortcuts
        if allowed(s.type, s.link_to)
    ]
    sections: list[dict[str, Any]] = []
    for row in doc.links:
        if row.type == "Card Break":
            sections.append({"label": row.label, "links": []})
        elif row.type == "Link" and sections and allowed(row.link_type, row.link_to):
            sections[-1]["links"].append(
                {
                    "label": row.label or row.link_to,
                    "type": row.link_type,
                    "name": row.link_to,
                    "is_query_report": int(row.is_query_report or 0),
                    "report_ref_doctype": row.report_ref_doctype or "",
                }
            )
    return {
        "workspace": name,
        "shortcuts": shortcuts,
        "sections": [section for section in sections if section["links"]],
    }


def build(segment: str) -> dict[str, Any]:
    """Everything the page needs for `/desk/zg-app/<segment>`; raises AppPageError(not_found / app_off / forbidden)."""
    from zatgo_core.services import app_authority

    app = find(segment)
    if not app:
        raise AppPageError("not_found", "Unknown app")
    enabled = is_enabled(app)
    if not enabled:
        raise AppPageError("app_off", f"{app['label']} is switched off on this site")
    page = overview(app)
    settings = settings_tabs(app)
    if page is None and not settings:
        raise AppPageError("forbidden", "Not permitted")
    tabs: list[dict[str, Any]] = []
    if page is not None:
        tabs.append({"key": OVERVIEW, "label": "Overview", "kind": "overview"})
    tabs.extend(settings)
    return {
        "app": {
            "key": app["key"],
            "route_key": app["route_key"],
            "label": app["label"],
            "icon": app["icon"],
            "description": app.get("description") or "",
            "version": app.get("version") or __version__,
            "kind": app["kind"],
        },
        "tabs": tabs,
        "overview": page,
        "warnings": warnings(app, app_state.switches(), enabled),
        "can_manage": app_authority.can_switch(),
        "hub": "/desk/zg-app-hub",
    }
