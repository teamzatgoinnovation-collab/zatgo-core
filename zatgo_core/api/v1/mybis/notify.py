"""MyBis -- notification choices and the notifications the system sent: invoice alerts and the daily report."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import parse_json_dict, require_login
from zatgo_core.services.mybis import delivery, notify_prefs


def _prefs() -> dict[str, Any]:
    chosen, allowed = notify_prefs.get(), notify_prefs.allowed()
    return {
        "prefs": [
            {"key": k, "label": notify_prefs.PREFS[k][0], "enabled": chosen[k], "allowed": allowed[k]} for k in notify_prefs.PREFS
        ]
    }


@frappe.whitelist(methods=["GET", "POST"])
def get_prefs() -> dict[str, Any]:
    """The caller's notification choices. `allowed: false` = the administrator switched that kind off for everyone."""
    require_login()
    return ok(_prefs())


@frappe.whitelist(methods=["POST"])
def set_prefs(prefs: Any = None) -> dict[str, Any]:
    """Save choices: `prefs` is a JSON object like {"sales_invoice": 1, "daily_report": 0}. Unknown keys are ignored."""
    require_login()
    notify_prefs.save(parse_json_dict(prefs) if prefs not in (None, "") else {})
    return ok(_prefs())


@frappe.whitelist(methods=["GET", "POST"])
def inbox(limit: int = 30) -> dict[str, Any]:
    """The caller's MyBis notifications, newest first: subject, body, the document it is about (to open it), read flag, time."""
    require_login()
    rows = delivery.mine(limit)
    return ok({"items": rows, "unread": sum(1 for r in rows if not r["read"])})


@frappe.whitelist(methods=["POST"])
def mark_read() -> dict[str, Any]:
    """Mark all of the caller's MyBis notifications read."""
    require_login()
    names = frappe.get_all(
        "Notification Log", filters={"for_user": frappe.session.user, "read": 0, "subject": ("like", delivery.TAG + "%")}, pluck="name"
    )
    for name in names:
        frappe.db.set_value("Notification Log", name, "read", 1, update_modified=False)
    return ok({"marked": len(names)})
