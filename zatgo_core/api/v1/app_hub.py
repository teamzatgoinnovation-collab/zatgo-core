"""ZatGo overview API -- every ZatGo app on this site, its state and where its settings are.

Paths:
  zatgo_core.api.v1.app_hub.get_hub
  zatgo_core.api.v1.app_hub.set_switch

Read by the Desk page `zg-app-hub`. Real data only: switch state, version, requirements, settings the caller
may open, and the conditions that mean an app is on but not set up. Authorization is server-side
(services/app_authority.py); the page's own checks are courtesy.
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import require_str
from zatgo_core.services import app_authority, app_catalog, app_page, app_state
from zatgo_core.services.ui_apps import SETTINGS, asset_url


def _can_see(app: dict[str, Any]) -> bool:
    roles = set(frappe.get_roles())
    return frappe.session.user == "Administrator" or bool(roles.intersection(app["roles"]))


def _settings_links(app: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"doctype": dt, "label": label, "route": "/desk/" + frappe.scrub(dt).replace("_", "-")}
        for dt, label in app["settings"]
        if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read")
    ]


def _warnings(app: dict[str, Any], on: dict[str, bool], enabled: bool) -> list[str]:
    """Why an app that is on is not (fully) set up (the page of the app shows the same list)."""
    return app_page.warnings(app, on, enabled)


def _serialise(app: dict[str, Any], on: dict[str, bool]) -> dict[str, Any]:
    has_switch = bool(app["switch_field"])
    enabled = bool(on.get(app["key"])) if has_switch else True
    return {
        "key": app["key"],
        "label": app["label"],
        "group": app["group"],
        "icon": app["icon"],
        "description": app["description"],
        "version": app["version"],
        "requires": [(app_catalog.get(k) or {"label": k})["label"] for k in app["requires"]],
        "has_switch": has_switch,
        "enabled": enabled,
        "settings": _settings_links(app),
        "warnings": _warnings(app, on, enabled),
    }


@frappe.whitelist()
def get_hub() -> dict[str, Any]:
    """Every app in the catalog with its state, and what the caller may open. System Manager only; the
    figures in `summary` are counted from the same rows the page shows."""
    if not app_authority.can_switch():
        return fail("forbidden", "System Manager only")
    on = app_state.switches()
    apps = [_serialise(a, on) for a in app_catalog.catalog() if _can_see(a)]
    switchable = [a for a in apps if a["has_switch"]]
    return ok(
        {
            "version": __version__,
            "css": asset_url("css/zg_app_hub.css"),
            "groups": list(app_catalog.GROUPS),
            "apps": apps,
            "summary": {
                "apps": len(apps),
                "enabled": sum(1 for a in switchable if a["enabled"]),
                "disabled": sum(1 for a in switchable if not a["enabled"]),
                "warnings": sum(len(a["warnings"]) for a in apps),
            },
            "load_errors": app_catalog.load_errors(),
        }
    )


@frappe.whitelist()
def set_switch(key: str, enabled: Any) -> dict[str, Any]:
    """Turn an app on / off for this site. Goes through ZG System Settings' own save, so its controller
    enforces who may do it, runs the set-up / Desk-entry sync and records the audit entry -- the same path
    as ticking the box there. Data is never deleted."""
    if not app_authority.can_switch():
        return fail("forbidden", "System Manager only")
    key = require_str(key, "key")
    field = app_catalog.switch_fields().get(key)
    if not field:
        return fail("unknown_switch", f"{key} has no on/off switch")
    doc = frappe.get_doc(SETTINGS)
    doc.set(field, 1 if frappe.utils.cint(enabled) else 0)
    doc.save()
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    return ok({"key": key, "enabled": app_state.is_on(key)})
