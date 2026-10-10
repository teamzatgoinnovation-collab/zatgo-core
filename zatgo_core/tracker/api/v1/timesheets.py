"""Team Timesheet drafts + submit for Sub/Top."""

from __future__ import annotations

import frappe
from frappe.utils import getdate

from zatgo_core.tracker.api.response import ok
from zatgo_core.tracker.permissions.capabilities import assert_can_manage_work, is_top
from zatgo_core.tracker.permissions.hierarchy import get_company_for_user, get_employee_for_user, get_subordinate_users
from zatgo_core.tracker.services.audit import log_event


def _team_employees(user: str | None = None) -> list[str]:
	user = user or frappe.session.user
	emps = set()
	self_emp = get_employee_for_user(user)
	if self_emp:
		emps.add(self_emp)
	# subordinates via users → employees
	for u in get_subordinate_users(user):
		e = get_employee_for_user(u)
		if e:
			emps.add(e)
	if is_top(user):
		company = get_company_for_user(user)
		if company:
			emps.update(
				frappe.get_all(
					"Employee",
					filters={"company": company, "status": "Active"},
					pluck="name",
				)
			)
	return list(emps)


@frappe.whitelist()
def list_team_drafts(from_date: str | None = None, to_date: str | None = None):
	assert_can_manage_work()
	emps = _team_employees()
	if not emps:
		return ok([])
	filters: dict = {"docstatus": 0}
	if from_date:
		filters["start_date"] = (">=", getdate(from_date))
	# Timesheet uses start_date / end_date — filter loosely
	rows = frappe.get_all(
		"Timesheet",
		filters={"docstatus": 0, "employee": ("in", emps)},
		fields=[
			"name",
			"employee",
			"employee_name",
			"start_date",
			"end_date",
			"total_hours",
			"status",
			"parent_project",
			"company",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=200,
	)
	if from_date or to_date:
		fd = getdate(from_date) if from_date else None
		td = getdate(to_date) if to_date else None
		filtered = []
		for r in rows:
			sd = getdate(r.start_date) if r.start_date else None
			ed = getdate(r.end_date) if r.end_date else sd
			if fd and ed and ed < fd:
				continue
			if td and sd and sd > td:
				continue
			filtered.append(r)
		rows = filtered
	return ok(rows)


@frappe.whitelist()
def submit_team(
	names: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
):
	"""Submit draft Timesheets for team. Pass names (CSV/JSON) or date range."""
	assert_can_manage_work()
	from zatgo_core.tracker.services.assign import parse_users

	targets = parse_users(names)
	if not targets:
		emps = _team_employees()
		if not emps:
			return ok({"submitted": [], "errors": []})
		rows = frappe.get_all(
			"Timesheet",
			filters={"docstatus": 0, "employee": ("in", emps)},
			pluck="name",
			limit_page_length=200,
		)
		# optional date filter via list_team_drafts envelope
		if from_date or to_date:
			draft_resp = list_team_drafts(from_date=from_date, to_date=to_date)
			data = (draft_resp or {}).get("data") or []
			targets = [r["name"] for r in data]
		else:
			targets = rows
	submitted = []
	errors = []
	emps = set(_team_employees())
	for name in targets:
		try:
			doc = frappe.get_doc("Timesheet", name)
			if int(doc.docstatus or 0) != 0:
				continue
			if doc.employee and doc.employee not in emps and not is_top():
				errors.append({"name": name, "error": "Not in your team"})
				continue
			doc.submit()
			log_event("Timesheet", name, action="submit_team")
			submitted.append(name)
		except Exception as e:
			errors.append({"name": name, "error": str(e)})
	return ok({"submitted": submitted, "errors": errors})
