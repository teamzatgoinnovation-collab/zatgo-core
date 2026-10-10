"""Role capability helpers for Tracker Worker / Sub / Top."""

from __future__ import annotations

import frappe
from frappe import _

from zatgo_core.tracker.permissions.roles import TRACKER_SUB, TRACKER_TOP, TRACKER_WORKER


def _roles(user: str | None = None) -> set[str]:
	user = user or frappe.session.user
	return set(frappe.get_roles(user))


def is_system(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return "System Manager" in _roles(user)


def is_top(user: str | None = None) -> bool:
	if is_system(user):
		return True
	return TRACKER_TOP in _roles(user)


def is_lead_or_above(user: str | None = None) -> bool:
	if is_system(user):
		return True
	roles = _roles(user)
	return TRACKER_TOP in roles or TRACKER_SUB in roles


def is_worker_only(user: str | None = None) -> bool:
	"""Has Worker role and neither Sub nor Top (nor System Manager)."""
	if is_system(user):
		return False
	roles = _roles(user)
	if TRACKER_TOP in roles or TRACKER_SUB in roles:
		return False
	return TRACKER_WORKER in roles


def assert_can_manage_work(user: str | None = None) -> None:
	"""Create / assign / delete / close — Sub, Top, or System Manager."""
	if not is_lead_or_above(user):
		frappe.throw(_("Only Team Leads and Managers can create or assign work."), frappe.PermissionError)


def assert_can_review(user: str | None = None) -> None:
	if not is_lead_or_above(user):
		frappe.throw(_("Only Team Leads and Managers can approve or request rework."), frappe.PermissionError)


def assert_is_top(user: str | None = None) -> None:
	if not is_top(user):
		frappe.throw(_("Only Managers (Tracker Top) can perform this action."), frappe.PermissionError)


def capability_payload(user: str | None = None) -> dict:
	user = user or frappe.session.user
	lead = is_lead_or_above(user)
	return {
		"can_manage_work": lead,
		"can_review": lead,
		"can_submit_timesheets": lead,
		"can_approve_timesheets": is_top(user),
		"can_close_project": is_top(user),
		"can_create_top": is_system(user),
		"can_assign_org": lead,
		"can_create_sub": lead,
		"can_create_worker": lead,
		"is_worker_only": is_worker_only(user),
		"is_top": is_top(user),
		"is_lead_or_above": lead,
	}
