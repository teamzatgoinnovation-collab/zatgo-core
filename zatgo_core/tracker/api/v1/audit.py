"""Audit list + org activity feed API."""

from __future__ import annotations

import frappe

from zatgo_core.tracker.api.response import fail, ok
from zatgo_core.tracker.services.audit import list_feed, list_for


@frappe.whitelist()
def list_for_doc(doctype: str, name: str, limit: int = 50):
	if not doctype or not name:
		return fail("bad_request", "doctype and name required")
	return ok(list_for(doctype, name, limit=limit))


@frappe.whitelist()
def feed(limit: int = 100, action: str | None = None, scope: str | None = None):
	"""Workbench activity feed for Worker / Sub / Top (scoped)."""
	return ok(list_feed(limit=limit, action=action, scope=scope))
