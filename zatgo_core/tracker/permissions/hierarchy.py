"""Org hierarchy helpers: Employee.reports_to tree + tracker_org_role."""

from __future__ import annotations

import frappe
from frappe import _


def get_employee_for_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return None
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def get_org_role(employee: str | None = None, user: str | None = None) -> str | None:
	emp = employee or get_employee_for_user(user)
	if not emp:
		return None
	if frappe.get_meta("Employee").has_field("tracker_org_role"):
		return frappe.db.get_value("Employee", emp, "tracker_org_role") or None
	return None


def get_company_for_user(user: str | None = None) -> str | None:
	emp = get_employee_for_user(user)
	if emp:
		company = frappe.db.get_value("Employee", emp, "company")
		if company:
			return company
	# Tracker Settings → user default → Global Defaults
	try:
		from zatgo_core.tracker.doctype.tracker_settings.tracker_settings import get_default_company

		settings_company = get_default_company()
		if settings_company:
			return settings_company
	except Exception:
		pass
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def get_subordinate_employees(manager_employee: str) -> set[str]:
	"""All employees below manager_employee in reports_to (transitive)."""
	if not manager_employee:
		return set()
	result: set[str] = set()
	frontier = [manager_employee]
	while frontier:
		parent = frontier.pop()
		children = frappe.get_all(
			"Employee",
			filters={"reports_to": parent, "status": "Active"},
			pluck="name",
		)
		for child in children:
			if child not in result:
				result.add(child)
				frontier.append(child)
	return result


def get_subordinate_users(manager_user: str | None = None) -> set[str]:
	manager_user = manager_user or frappe.session.user
	emp = get_employee_for_user(manager_user)
	if not emp:
		return set()
	subs = get_subordinate_employees(emp)
	if not subs:
		return set()
	users = frappe.get_all(
		"Employee",
		filters={"name": ("in", list(subs)), "user_id": ("is", "set")},
		pluck="user_id",
	)
	return {u for u in users if u}


def can_assign_to(assigner: str, assignee: str) -> bool:
	"""Assigner may assign to self or anyone strictly below in reports_to."""
	if not assigner or not assignee:
		return False
	if assigner == assignee:
		return True
	if assigner == "Administrator" or "System Manager" in frappe.get_roles(assigner):
		return True
	return assignee in get_subordinate_users(assigner)


def assert_can_assign(assigner: str, assignee: str) -> None:
	if not can_assign_to(assigner, assignee):
		frappe.throw(
			_(
				"Cannot assign to {0}. You can only assign to yourself or people below you in the org tree."
			).format(assignee),
			frappe.PermissionError,
		)
