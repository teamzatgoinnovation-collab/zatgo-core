"""Validation for ZG Application Settings (client apps)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document

_APP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLATFORMS = {"Electron", "Flutter", "Web", "All"}


def validate_application_settings(doc: Document) -> None:
    """Ensure client app keys are unique and valid for this site."""
    seen: set[str] = set()
    for row in doc.get("client_apps") or []:
        key = (row.app_key or "").strip()
        if not key:
            frappe.throw(frappe._("App Key is required on every client application row"))
        if not _APP_KEY_RE.match(key):
            frappe.throw(
                frappe._(
                    "App Key {0} must be lowercase snake_case (Electron/Flutter/Web product id)"
                ).format(key)
            )
        if key in seen:
            frappe.throw(frappe._("Duplicate client App Key {0}").format(key))
        seen.add(key)

        if not (row.title or "").strip():
            frappe.throw(frappe._("Title is required for {0}").format(key))

        if row.platform not in _PLATFORMS:
            frappe.throw(frappe._("Invalid platform for {0}").format(key))

        if row.config_json:
            try:
                parsed = json.loads(row.config_json)
            except json.JSONDecodeError as exc:
                frappe.throw(
                    frappe._("Invalid App Config JSON for {0}: {1}").format(key, exc)
                )
            if not isinstance(parsed, dict):
                frappe.throw(
                    frappe._("App Config JSON for {0} must be an object").format(key)
                )

    default_app = (doc.default_client_app or "").strip()
    if default_app and default_app not in seen and (doc.get("client_apps") or []):
        frappe.throw(
            frappe._("Default Client App {0} must match an App Key in the table").format(
                default_app
            )
        )
