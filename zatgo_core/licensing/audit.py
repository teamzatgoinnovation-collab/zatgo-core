"""Licence events in ZG Audit Log (brief Part 17): imported, replaced, verification failed, revoked, issued.

One row per event: `doctype_name` = the DocType concerned, `fieldname` = the event, `new_value` = a JSON
summary. Never a key, never a whole licence file -- ids, numbers, hashes and reasons only.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import frappe


def log(event: str, doctype: str, name: str | None, details: Mapping[str, Any], reason: str = "",
        durable: bool = False) -> None:
    """`durable`: the caller is about to raise, and Frappe rolls the request back on an error -- commit this row
    on its own so a refused import is still on record (only inside a web request; never in tests or jobs)."""
    request = getattr(frappe.local, "request", None)
    try:
        frappe.get_doc({
            "doctype": "ZG Audit Log",
            "doctype_name": doctype,
            "document_name": name or "",
            "fieldname": event,
            "old_value": None,
            "new_value": json.dumps(dict(details), sort_keys=True, default=str),
            "changed_by": frappe.session.user,
            "change_date": frappe.utils.today(),
            "change_time": frappe.utils.nowtime(),
            "ip_address": getattr(request, "remote_addr", None) if request else None,
            "reason": reason[:500],
            "app_name": "zatgo_core",
        }).insert(ignore_permissions=True)
        if durable and request is not None and not frappe.flags.in_test:
            frappe.db.commit()  # nosemgrep: audit row of a refusal that is about to roll the request back
    except Exception:
        frappe.logger("zatgo_core").exception("licence audit log failed")
