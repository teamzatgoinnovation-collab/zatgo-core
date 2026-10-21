"""Load Chat AI Settings as a plain dict (passwords resolved)."""

from __future__ import annotations

import frappe
from frappe.utils import cint


def local_only_enabled() -> bool:
    """'Local models only' for this site. ON unless a saved settings form explicitly has it off.

    `doc.as_dict()` can't tell "never saved" from "unticked": Frappe turns a missing Check value into
    0, which would switch the protection off on every site that predates the field. A saved form
    stores its checkboxes (0 or 1); a site that never saved the field has no row at all."""
    row = frappe.db.sql(
        "select value from `tabSingles` where doctype = %s and field = %s", ("Chat AI Settings", "local_only")
    )
    value = row[0][0] if row else None
    # An empty value is "not set" (a saved, unticked checkbox stores 0), so it is ON too.
    return True if value in (None, "") else cint(value) != 0


def get_settings_dict() -> dict:
    try:
        doc = frappe.get_single("Chat AI Settings")
    except Exception:
        return {}
    data = doc.as_dict()
    data["local_only"] = 1 if local_only_enabled() else 0
    # Resolve passwords
    for field in ("api_key", "embedding_api_key", "web_search_api_key"):
        try:
            data[field] = doc.get_password(field) if doc.get(field) else ""
        except Exception:
            data[field] = ""
    return data
