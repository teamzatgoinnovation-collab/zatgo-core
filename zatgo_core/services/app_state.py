"""Which apps are on for this site -- the one place that answers "is app X on here?".

State lives in ZG System Settings (one Check field per switchable app, see services/app_catalog.py); an app
with no switch is always on. Everything that gates on an app -- hooks, API prefixes, the sidebar, the hub --
asks here, so there is exactly one rule.

An app declared `default_on` (VanSaleX: it was always on before it got a switch) counts as ON where its field
has no stored value. A Check on a Single reads 0 both when it is stored as 0 and when nothing is stored, so
for those apps the stored value is read from `tabSingles` itself -- the same "no row = on" rule as
events/default_source_warehouse.autofill_enabled. A site that has not migrated yet therefore keeps running
what it always had; patch v0_4_7 stores the 1 so the form shows what is enforced.

Settings that cannot be read (mid migrate) switch every app off except the `default_on` ones.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from zatgo_core.services import app_catalog

SETTINGS = "ZG System Settings"


def _settings_doc() -> Any | None:
    try:
        return frappe.get_cached_doc(SETTINGS)
    except Exception:
        return None


def switch_state(doc: Any | None, app: dict[str, Any]) -> bool:
    """Is `app` on according to the settings document `doc` (or a before-save copy of it)? Only a document
    cannot tell "stored 0" from "nothing stored" -- see `switches` for the site's real state."""
    field = app["switch_field"]
    if not field:
        return True
    value = doc.get(field) if doc is not None else None
    return bool(value) if value is not None else bool(app["default_on"])


def switches_of(doc: Any | None) -> dict[str, bool]:
    """key -> on/off for every app that has a switch, as `doc` (a ZG System Settings document or a
    before-save copy of it) has them."""
    return {a["key"]: switch_state(doc, a) for a in app_catalog.catalog() if a["switch_field"]}


def _stored(fields: list[str]) -> dict[str, str]:
    """field -> stored value, for the fields that have one."""
    try:
        rows = frappe.db.sql(
            "select field, value from `tabSingles` where doctype = %s and field in %s",
            (SETTINGS, tuple(fields)),
        )
    except Exception:
        return {}
    return {field: value for field, value in rows}


def switches() -> dict[str, bool]:
    """This site's switches: key -> on/off for every app that has a switch."""
    state = switches_of(_settings_doc())
    defaults = [a for a in app_catalog.catalog() if a["switch_field"] and a["default_on"]]
    if defaults:
        stored = _stored([a["switch_field"] for a in defaults])
        for a in defaults:
            raw = stored.get(a["switch_field"])
            state[a["key"]] = True if raw is None else bool(cint(raw))  # nothing stored: the default
    return state


def is_on(key: str) -> bool:
    """One app. Unknown keys are off; an app without a switch is on."""
    app = app_catalog.get(key)
    if app is None:
        return False
    if app["switch_field"] and app["default_on"]:
        raw = _stored([app["switch_field"]]).get(app["switch_field"])
        if raw is None:
            return True
        return bool(cint(raw))
    return switch_state(_settings_doc(), app)
