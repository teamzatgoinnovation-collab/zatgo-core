"""Activity start / pause / stop / active."""

from __future__ import annotations

import frappe

from zatgo_core.tracker.api.response import fail, ok
from zatgo_core.tracker.services import activity as activity_service


@frappe.whitelist()
def active():
	return ok(activity_service.get_active_session())


@frappe.whitelist()
def activity_types():
	"""Activity Type options for Start (timesheet billing codes)."""
	rows = frappe.get_all(
		"Activity Type",
		fields=["name", "activity_type", "billing_rate", "costing_rate", "disabled"],
		order_by="name asc",
		limit_page_length=200,
	)
	# ERPNext Activity Type often uses name == activity_type label
	out = []
	for r in rows:
		if r.get("disabled"):
			continue
		out.append(
			{
				"name": r.get("name"),
				"label": r.get("activity_type") or r.get("name"),
				"billing_rate": r.get("billing_rate"),
				"costing_rate": r.get("costing_rate"),
			}
		)
	default = None
	try:
		from zatgo_core.tracker.doctype.tracker_settings.tracker_settings import get_default_activity_type

		default = get_default_activity_type()
	except Exception:
		default = "Execution"
	return ok({"items": out, "default": default})


@frappe.whitelist()
def start(task: str | None = None, project: str | None = None, activity_type: str | None = None):
	if not task and not project:
		return fail("bad_request", "task or project required")
	return ok(
		activity_service.start_session(
			task=task, project=project, activity_type=activity_type
		)
	)


@frappe.whitelist()
def pause(name: str | None = None):
	return ok(activity_service.pause_session(name))


@frappe.whitelist()
def stop(name: str | None = None):
	return ok(activity_service.stop_session(name, flush=True))


@frappe.whitelist()
def running_now(company: str | None = None):
	"""Who is Running right now (company-scoped)."""
	return ok(activity_service.list_running_sessions(company=company))
