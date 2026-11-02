"""Live duplicate lookup for the Desk form (public/js/zg_duplicate_lookup.js) and API clients.

Authenticated, create/write permission on the DocType required, results filtered by the caller's own read
permissions (services/duplicate/matcher.present) -- a record the caller cannot read is reported as
restricted, without ID or details."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from zatgo_core.api.response import ok
from zatgo_core.services.duplicate import config, enforcement, matcher

_MAX_VALUE_LENGTH = 200
_MAX_CHILD_ROWS = 50


def _require(doctype: str) -> dict[str, Any]:
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)
    if not (frappe.has_permission(doctype, "create") or frappe.has_permission(doctype, "write")):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    rule = config.rule_for(doctype)
    if not rule:
        frappe.throw(_("Duplicate prevention is not configured for {0}").format(_(doctype)), frappe.DoesNotExistError)
    return rule


def _clean(values: Any) -> dict[str, Any]:
    if isinstance(values, str):
        values = json.loads(values or "{}")
    if not isinstance(values, dict):
        frappe.throw(_("values must be an object"), frappe.ValidationError)
    out: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, list):
            out[str(key)] = [{str(k): str(v)[:_MAX_VALUE_LENGTH] for k, v in row.items() if v is not None}
                             for row in value[:_MAX_CHILD_ROWS] if isinstance(row, dict)]
        elif value is not None and not isinstance(value, dict):
            out[str(key)] = str(value)[:_MAX_VALUE_LENGTH]
    return out


@frappe.whitelist(methods=["GET", "POST"])
def form_config(doctype: str) -> dict[str, Any]:
    """What the form script needs: whether to look up live, which fields to watch (rule fields, in the
    form's own field and child-table names), and whether this user may override."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)
    rule = config.rule_for(doctype)
    live = bool(rule and rule["live"] and config.settings()["live_lookup"])
    watch = sorted({s["child_table"] if s["source"] == "Child Table" else s["fieldname"] for s in rule["fields"]}) if rule else []
    meta = frappe.get_meta(doctype)
    children = sorted({(meta.get_field(s["child_table"]).options, s["fieldname"], s["child_table"]) for s in rule["fields"]
                       if s["source"] == "Child Table" and meta.get_field(s["child_table"])}) if rule else []
    return ok({"live": live, "watch": watch, "children": [{"doctype": d, "fieldname": f, "table": t} for d, f, t in children], "can_override": bool(rule and enforcement.can_override(rule)),
               "needs_reason": config.settings()["override_needs_reason"],
               "strong_action": rule["strong_action"] if rule else None, "possible_action": rule["possible_action"] if rule else None})


@frappe.whitelist(methods=["POST"])
def check(doctype: str, values: Any = None, exclude: str | None = None) -> dict[str, Any]:
    rule = _require(doctype)
    found = matcher.find_matches(doctype, _clean(values), exclude, rule=rule)
    level = matcher.worst(found)
    action = {matcher.STRONG: rule["strong_action"], matcher.POSSIBLE: rule["possible_action"]}.get(level or "", "Suggest")
    return ok({"level": level, "action": action, "matches": matcher.present(doctype, found, rule),
               "can_override": enforcement.can_override(rule)})


@frappe.whitelist(methods=["POST"])
def override(doctype: str, names: Any, reason: str = "") -> dict[str, Any]:
    """Record that the caller accepts these existing records as non-duplicates; the next save of a
    matching new document by the same user (within 10 minutes) goes through and is logged."""
    rule = _require(doctype)
    if not enforcement.can_override(rule):
        frappe.throw(_("You are not authorized to override duplicate prevention"), frappe.PermissionError)
    names = json.loads(names) if isinstance(names, str) else names
    if config.settings()["override_needs_reason"] and not (reason or "").strip():
        frappe.throw(_("A reason is required"), frappe.ValidationError)
    enforcement.register_override(doctype, [str(n) for n in names][:50], (reason or "")[:500])
    return ok({"registered": True})
