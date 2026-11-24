"""Capability contract for ZatGo's clients (licensing/capabilities.py, docs/licensing.md "Client contract").

Path: zatgo_core.api.v1.licensing.capabilities.get   (any logged-in user; optional `platform`: desk |
desktop | mobile). A hint for what to show: the server enforces every rule whatever a client hides.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from zatgo_core.api.response import ok
from zatgo_core.licensing import capabilities


@frappe.whitelist()
def get(platform: str | None = None) -> dict[str, Any]:
    if frappe.session.user == "Guest":
        frappe.throw(_("Log in first."), frappe.PermissionError)
    return ok(capabilities.for_user(platform))
