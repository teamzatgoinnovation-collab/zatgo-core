"""App Settings Hub API -- one place to see and switch every sub-app.

Paths:
  zatgo_core.api.v1.app_hub.get_hub
  zatgo_core.api.v1.app_hub.set_switch
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import require_str
from zatgo_core.services import app_catalog
from zatgo_core.services.ui_apps import SETTINGS, switches


def _is_manager() -> bool:
    return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def _can_see(app: dict[str, Any]) -> bool:
    roles = set(frappe.get_roles())
    return frappe.session.user == "Administrator" or bool(roles.intersection(app["roles"]))


def _serialise(app: dict[str, Any], on: dict[str, bool]) -> dict[str, Any]:
    has_switch = bool(app["switch_field"])
    settings = [
        {"doctype": dt, "label": label, "route": "/app/" + frappe.scrub(dt).replace("_", "-")}
        for dt, label in app["settings"]
        if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read")
    ]
    return {
        "key": app["key"],
        "label": app["label"],
        "group": app["group"],
        "icon": app["icon"],
        "description": app["description"],
        "has_switch": has_switch,
        "enabled": bool(on.get(app["key"])) if has_switch else True,
        "settings": settings,
    }


@frappe.whitelist()
def get_hub() -> dict[str, Any]:
    """Every app in the catalog with its switch state and the settings
    DocTypes the caller may open."""
    if not _is_manager():
        return fail("forbidden", "System Manager only")
    on = switches()
    return ok(
        {
            "groups": list(app_catalog.GROUPS),
            "apps": [_serialise(a, on) for a in app_catalog.catalog() if _can_see(a)],
        }
    )


@frappe.whitelist()
def set_switch(key: str, enabled: Any) -> dict[str, Any]:
    """Turn a sub-app on / off for this site. Goes through ZG System Settings'
    own save, so on_update does the set-up / Desk-entry removal -- the same
    path as ticking the box there. Data is never deleted."""
    if not _is_manager():
        return fail("forbidden", "System Manager only")
    key = require_str(key, "key")
    field = app_catalog.switch_fields().get(key)
    if not field:
        return fail("unknown_switch", f"{key} has no on/off switch")
    doc = frappe.get_doc(SETTINGS)
    doc.set(field, 1 if frappe.utils.cint(enabled) else 0)
    doc.save()
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    return ok({"key": key, "enabled": bool(switches().get(key))})
