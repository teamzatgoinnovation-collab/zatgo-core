"""Settings Map API -- every app's settings with controls, scope and status; change one field.

Paths:
  zatgo_core.api.v1.settings_map.get_map
  zatgo_core.api.v1.settings_map.save_field

Read and written by the Desk page `zg-settings-map`. The page's checks are courtesy: `services/settings_map.py` decides
(DocType in an app manifest, write permission, no secrets / tables / attachments / app switches), and the DocType's own save
validates the value.
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import require_str
from zatgo_core.services import settings_map
from zatgo_core.services.ui_apps import asset_url


@frappe.whitelist()
def get_map(app: str | None = None) -> dict[str, Any]:
    """Apps the caller may see with their settings; `app` limits it to one app key."""
    data = settings_map.describe((app or "").strip() or None)
    data["css"] = asset_url("css/zg_settings_map.css")
    return ok(data)


@frappe.whitelist(methods=["POST"])
def save_field(doctype: str, fieldname: str, value: Any = None) -> dict[str, Any]:
    """Change one field of an app's settings through its document save."""
    try:
        return ok(settings_map.save_field(require_str(doctype, "doctype"), require_str(fieldname, "fieldname"), value))
    except settings_map.SettingsMapError as exc:
        return fail(exc.code, exc.message)
