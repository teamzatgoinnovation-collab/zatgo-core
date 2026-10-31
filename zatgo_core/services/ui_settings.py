"""Brand, theme and default language: the settings of the Desk Theme and Language Switcher apps.

They used to be fields of ZG System Settings; each app owns its own now (ZG Theme Settings, ZG Language Settings,
patches/v0_4_10). `values()` is what the rest of the code reads: the app's own settings, and -- on a site whose
database is not migrated yet (the new DocTypes have no table) -- the old fields, so a deploy that copies the code
before the migrate keeps working.
"""

from __future__ import annotations

import frappe

LEGACY = "ZG System Settings"
OWNERS = {
    "ZG Theme Settings": ("brand_name", "company_logo", "theme"),
    "ZG Language Settings": ("language",),
}


def _legacy(field: str):
    try:
        return frappe.db.get_single_value(LEGACY, field)
    except Exception:
        return None


def values() -> dict[str, str | None]:
    """brand_name, company_logo, theme, language -- each from its owner app's settings."""
    out: dict[str, str | None] = {}
    for doctype, fields in OWNERS.items():
        try:
            doc = frappe.get_cached_doc(doctype)
        except Exception:
            doc = None
        for field in fields:
            out[field] = doc.get(field) if doc is not None else _legacy(field)
    return out
