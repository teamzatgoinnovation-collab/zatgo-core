"""Whitelisted API for ZatGo AI scheduled tasks (the Desk list/form does the rest)."""

from __future__ import annotations

import frappe
from frappe import _

from zatgo_core.chat_ai.api.response import fail, ok


@frappe.whitelist()
def run_now(name=None):
	"""Queue one run of the task now. Owner or manager only (checked by the document permission)."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)
	from zatgo_core.chat_ai.erpnext import scheduled_tasks

	if not frappe.db.exists(scheduled_tasks.DOCTYPE, name):
		return fail(_("Task not found"), code="not_found")
	if not scheduled_tasks.run_now(name):
		return fail(_("This task is already queued or running."), code="busy")
	return ok({"queued": name})
