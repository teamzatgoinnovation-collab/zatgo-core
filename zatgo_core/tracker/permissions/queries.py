"""Permission query conditions — company + hierarchy scoped."""

from __future__ import annotations

import frappe

from zatgo_core.tracker.permissions.hierarchy import (
	get_company_for_user,
	get_employee_for_user,
	get_subordinate_users,
)


def _is_privileged(user: str) -> bool:
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	return bool(roles & {"System Manager", "Tracker Top"})


def _company_clause(alias: str = "company") -> str:
	company = get_company_for_user()
	if not company:
		return "1=0"
	return f"`tab{{doctype}}`.`{alias}` = {frappe.db.escape(company)}"


def project_permission_query(user: str) -> str:
	if not user or user == "Guest":
		return "1=0"
	if _is_privileged(user):
		company = get_company_for_user(user)
		if company and "System Manager" not in frappe.get_roles(user) and user != "Administrator":
			return f"`tabProject`.`company` = {frappe.db.escape(company)}"
		return ""
	company = get_company_for_user(user)
	if not company:
		return "1=0"
	# member of project or company match
	return (
		f"`tabProject`.`company` = {frappe.db.escape(company)} "
		f"AND (`tabProject`.`name` IN ("
		f"SELECT parent FROM `tabProject User` WHERE user = {frappe.db.escape(user)}"
		f") OR EXISTS ("
		f"SELECT 1 FROM `tabToDo` WHERE reference_type='Project' "
		f"AND reference_name=`tabProject`.`name` AND allocated_to={frappe.db.escape(user)}"
		f"))"
	)


def task_permission_query(user: str) -> str:
	if not user or user == "Guest":
		return "1=0"
	if _is_privileged(user):
		company = get_company_for_user(user)
		if company and user != "Administrator" and "System Manager" not in frappe.get_roles(user):
			return f"`tabTask`.`company` = {frappe.db.escape(company)}"
		return ""
	company = get_company_for_user(user)
	if not company:
		return "1=0"
	return (
		f"`tabTask`.`company` = {frappe.db.escape(company)} "
		f"AND (`tabTask`.`_assign` LIKE {frappe.db.escape('%' + user + '%')} "
		f"OR `tabTask`.`owner` = {frappe.db.escape(user)})"
	)


def issue_permission_query(user: str) -> str:
	if not user or user == "Guest":
		return "1=0"
	if _is_privileged(user):
		company = get_company_for_user(user)
		if company and user != "Administrator" and "System Manager" not in frappe.get_roles(user):
			return f"`tabIssue`.`company` = {frappe.db.escape(company)}"
		return ""
	company = get_company_for_user(user)
	if not company:
		return "1=0"
	return (
		f"`tabIssue`.`company` = {frappe.db.escape(company)} "
		f"AND (`tabIssue`.`raised_by` = {frappe.db.escape(user)} "
		f"OR `tabIssue`.`_assign` LIKE {frappe.db.escape('%' + user + '%')})"
	)


def timesheet_permission_query(user: str) -> str:
	if not user or user == "Guest":
		return "1=0"
	if _is_privileged(user):
		return ""
	emp = get_employee_for_user(user)
	if not emp:
		return "1=0"
	subs = get_subordinate_users(user)
	employees = {emp}
	if subs:
		more = frappe.get_all("Employee", filters={"user_id": ("in", list(subs))}, pluck="name")
		employees.update(more)
	escaped = ", ".join(frappe.db.escape(e) for e in employees)
	return f"`tabTimesheet`.`employee` IN ({escaped})"


def activity_session_permission_query(user: str) -> str:
	if not user or user == "Guest":
		return "1=0"
	if _is_privileged(user):
		return ""
	subs = get_subordinate_users(user)
	users = {user} | subs
	escaped = ", ".join(frappe.db.escape(u) for u in users)
	return f"`tabTracker Activity Session`.`user` IN ({escaped})"


def project_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _is_privileged(user):
		return True
	company = get_company_for_user(user)
	return bool(company and doc.company == company)


def task_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _is_privileged(user):
		return True
	company = get_company_for_user(user)
	if not company or doc.company != company:
		return False
	assign = doc.get("_assign") or ""
	return user in assign or doc.owner == user


def issue_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _is_privileged(user):
		return True
	company = get_company_for_user(user)
	if not company or doc.company != company:
		return False
	assign = doc.get("_assign") or ""
	return user in assign or doc.raised_by == user


def timesheet_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _is_privileged(user):
		return True
	emp = get_employee_for_user(user)
	return bool(emp and doc.employee == emp)


def activity_session_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _is_privileged(user):
		return True
	if doc.user == user:
		return True
	return doc.user in get_subordinate_users(user)
