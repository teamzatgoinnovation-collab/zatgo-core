"""Duplicate-prevention configuration -- rules and settings as plain dicts, cached.

Only non-sensitive configuration (which fields to compare, which action to take) is cached; never record data.
`clear_cache` is called from the settings / rule controllers.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

APP_KEY = "duplicate_prevention"
SETTINGS = "ZG Duplicate Prevention Settings"
RULE = "ZG Duplicate Rule"
_RULES_KEY = "zg_duplicate_rules"
_SETTINGS_KEY = "zg_duplicate_settings"

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "live_lookup": True,
    "fuzzy_threshold": 0.85,
    "result_limit": 8,
    "scan_limit": 50000,
    "override_roles": ["System Manager"],
    "override_needs_reason": True,
}


def clear_cache() -> None:
    frappe.cache.delete_value(_RULES_KEY)
    frappe.cache.delete_value(_SETTINGS_KEY)


def _single_has_rows() -> bool:
    return bool(frappe.db.sql("select 1 from `tabSingles` where doctype = %s limit 1", SETTINGS))


def settings() -> dict[str, Any]:
    """Global settings. A site that never saved the Single gets the defaults (enabled)."""
    cached = frappe.cache.get_value(_SETTINGS_KEY)
    if cached is not None:
        return cached
    values = dict(DEFAULT_SETTINGS)
    try:
        if _single_has_rows():
            doc = frappe.get_doc(SETTINGS)
            values.update(
                enabled=bool(cint(doc.enabled)),
                live_lookup=bool(cint(doc.live_lookup)),
                fuzzy_threshold=flt(doc.fuzzy_threshold or 85) / 100,
                result_limit=min(25, max(1, cint(doc.result_limit) or 8)),
                scan_limit=cint(doc.scan_limit),
                override_roles=[r.role for r in doc.override_roles] or ["System Manager"],
                override_needs_reason=bool(cint(doc.override_needs_reason)),
            )
    except Exception:  # mid-migrate: tables not there yet -- run with defaults, cache nothing
        return values
    frappe.cache.set_value(_SETTINGS_KEY, values)
    return values


def _load_rules() -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for name in frappe.get_all(RULE, filters={"enabled": 1}, pluck="name"):
        doc = frappe.get_doc(RULE, name)
        fields = [
            {
                "fieldname": r.fieldname,
                "kind": r.kind,
                "role": r.match_role,
                "source": r.source or "Document",
                "child_table": r.child_table,
                "group": (r.match_group or "").strip(),
                "show": bool(cint(r.show_in_results)),
            }
            for r in doc.fields
            if not cint(r.excluded)
        ]
        rules[doc.ref_doctype] = {
            "doctype": doc.ref_doctype,
            "type": doc.rule_type,
            "live": bool(cint(doc.live_lookup)),
            "strong_action": doc.strong_action,
            "possible_action": doc.possible_action,
            "fuzzy": bool(cint(doc.fuzzy_suggest)),
            "fields": fields,
            "display_fields": doc.display_list(),
            "override_roles": [r.role for r in doc.override_roles],
        }
    return rules


def rules() -> dict[str, dict[str, Any]]:
    cached = frappe.cache.get_value(_RULES_KEY)
    if cached is not None:
        return cached
    try:
        loaded = _load_rules()
    except Exception:  # tables missing (mid-install / migrate)
        return {}
    frappe.cache.set_value(_RULES_KEY, loaded)
    return loaded


def is_active() -> bool:
    """App switch + global switch. Never raises: a hook must not break a save because config is unreadable."""
    from zatgo_core.services import app_state

    try:
        return app_state.is_on(APP_KEY) and settings()["enabled"]
    except Exception:
        return False


def rule_for(doctype: str) -> dict[str, Any] | None:
    if not is_active():
        return None
    rule = rules().get(doctype)
    return rule if rule and rule["fields"] else None


def override_roles(rule: dict[str, Any]) -> list[str]:
    return rule["override_roles"] or settings()["override_roles"]
