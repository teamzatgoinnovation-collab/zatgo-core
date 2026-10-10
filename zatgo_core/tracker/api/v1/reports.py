"""Light Timesheet hour reports for Tracker."""

from __future__ import annotations

import frappe
from frappe.utils import getdate

from zatgo_core.tracker.api.response import fail, ok, paginated
from zatgo_core.tracker.permissions.capabilities import is_lead_or_above, is_top, is_worker_only
from zatgo_core.tracker.permissions.hierarchy import (
	get_company_for_user,
	get_employee_for_user,
	get_subordinate_employees,
	get_subordinate_users,
)
from zatgo_core.tracker.services.review import enrich_task_row


def _allowed_employees(user: str | None = None) -> list[str] | None:
	"""None = unrestricted (System Manager); else self + subordinates."""
	user = user or frappe.session.user
	if user in ("Administrator",) or "System Manager" in frappe.get_roles(user):
		return None
	emp = get_employee_for_user(user)
	if not emp:
		return []
	subs = get_subordinate_employees(emp)
	return [emp, *sorted(subs)]


def _parse_dates(from_date, to_date):
	if not from_date or not to_date:
		return None, None, fail("bad_request", "from_date and to_date required")
	try:
		fd, td = getdate(from_date), getdate(to_date)
		if fd > td:
			return None, None, fail("bad_request", "from_date must be on or before to_date")
		return fd, td, None
	except Exception:
		return None, None, fail("bad_request", "invalid date")


def _timesheet_scope(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 50,
):
	"""Shared date/company/employee scope for Timesheet Detail reports."""
	fd, td, err = _parse_dates(from_date, to_date)
	if err:
		return None
	page = int(page or 1)
	page_size = min(int(page_size or 50), 500)
	company = company or get_company_for_user()
	employees = _allowed_employees()
	conds = ["ts.docstatus < 2", "td.hours > 0", "DATE(td.from_time) BETWEEN %(fd)s AND %(td)s"]
	vals: dict = {"fd": fd, "td": td}
	if company:
		conds.append("ts.company = %(company)s")
		vals["company"] = company
	if employees is not None:
		if not employees:
			return {
				"empty": True,
				"page": page,
				"page_size": page_size,
			}
		conds.append("ts.employee IN %(employees)s")
		vals["employees"] = employees
	return {
		"empty": False,
		"page": page,
		"page_size": page_size,
		"where": " AND ".join(conds),
		"vals": vals,
		"err": None,
	}


def _paginate(rows: list, page: int, page_size: int):
	total = len(rows)
	start = (page - 1) * page_size
	return rows[start : start + page_size], total


@frappe.whitelist()
def overview(status: str | None = None):
	"""Lead dashboard: task counts, filtered items, running sessions, draft timesheets."""
	user = frappe.session.user
	status = status or "Pending Review"

	if is_worker_only(user) or not is_lead_or_above(user):
		return ok(
			{
				"counts": {},
				"status": status,
				"items": [],
				"running": 0,
				"timesheet_drafts": 0,
			}
		)

	company = get_company_for_user(user)
	# Top / System: company-wide; Sub: team assignees
	company_scope = is_top(user)

	base_filters: dict = {}
	or_filters = None
	if company:
		base_filters["company"] = company
	if not company_scope:
		team_users = get_subordinate_users(user) | {user}
		or_filters = [["_assign", "like", f"%{u}%"] for u in team_users]

	# Counts by ERPNext Task status
	counts: dict[str, int] = {}
	conds = ["1=1"]
	vals: dict = {}
	if company:
		conds.append("company = %(company)s")
		vals["company"] = company
	if not company_scope:
		team_users = list(get_subordinate_users(user) | {user})
		if not team_users:
			status_rows = []
		else:
			# Filter tasks assigned to team via _assign LIKE any user
			like_parts = []
			for i, u in enumerate(team_users):
				key = f"u{i}"
				like_parts.append(f"_assign LIKE %({key})s")
				vals[key] = f"%{u}%"
			conds.append("(" + " OR ".join(like_parts) + ")")
			status_rows = frappe.db.sql(
				f"""
				SELECT status, COUNT(*) AS cnt
				FROM `tabTask`
				WHERE {" AND ".join(conds)}
				GROUP BY status
				""",
				vals,
				as_dict=True,
			)
	else:
		status_rows = frappe.db.sql(
			f"""
			SELECT status, COUNT(*) AS cnt
			FROM `tabTask`
			WHERE {" AND ".join(conds)}
			GROUP BY status
			""",
			vals,
			as_dict=True,
		)
	for row in status_rows:
		key = row.get("status") or "Open"
		counts[key] = int(row.get("cnt") or 0)

	item_filters = dict(base_filters)
	item_filters["status"] = status
	items = frappe.get_all(
		"Task",
		filters=item_filters,
		or_filters=or_filters,
		fields=[
			"name",
			"subject",
			"status",
			"priority",
			"project",
			"company",
			"exp_end_date",
			"modified",
			"_assign",
		],
		order_by="modified desc",
		limit_page_length=50,
	)
	items = [enrich_task_row(r) for r in items]

	# Running activity sessions (company when Top; team users when Sub)
	if company_scope:
		running_filters: dict = {"status": "Running"}
		if company:
			running_filters["company"] = company
		running = frappe.db.count("Tracker Activity Session", running_filters)
	else:
		team_users = get_subordinate_users(user) | {user}
		running = frappe.db.count(
			"Tracker Activity Session",
			{"status": "Running", "user": ("in", list(team_users))},
		)

	# Draft timesheets for leads
	from zatgo_core.tracker.api.v1.timesheets import _team_employees

	emps = _team_employees(user)
	timesheet_drafts = 0
	if emps:
		timesheet_drafts = frappe.db.count(
			"Timesheet",
			{"docstatus": 0, "employee": ("in", emps)},
		)

	return ok(
		{
			"counts": counts,
			"status": status,
			"items": items,
			"running": int(running or 0),
			"timesheet_drafts": int(timesheet_drafts or 0),
		}
	)


@frappe.whitelist()
def hours_by_project(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 50,
):
	scope = _timesheet_scope(from_date, to_date, company, page, page_size)
	if scope is None:
		fd, td, err = _parse_dates(from_date, to_date)
		return err
	if scope.get("empty"):
		return paginated([], page=scope["page"], page_size=scope["page_size"], total=0)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(td.project, ts.parent_project, '') AS project,
			SUM(td.hours) AS hours,
			COUNT(*) AS entries,
			COUNT(DISTINCT ts.employee) AS people,
			COUNT(DISTINCT ts.name) AS timesheets
		FROM `tabTimesheet Detail` td
		INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		WHERE {scope["where"]}
		GROUP BY COALESCE(td.project, ts.parent_project, '')
		ORDER BY hours DESC
		""",
		scope["vals"],
		as_dict=True,
	)
	slice_rows, total = _paginate(rows, scope["page"], scope["page_size"])
	for r in slice_rows:
		r["hours"] = float(r.get("hours") or 0)
		r["entries"] = int(r.get("entries") or 0)
		r["people"] = int(r.get("people") or 0)
		r["timesheets"] = int(r.get("timesheets") or 0)
		r["project"] = r.get("project") or None
		if r["project"]:
			r["project_name"] = frappe.db.get_value("Project", r["project"], "project_name") or r["project"]
		else:
			r["project_name"] = None
	return paginated(slice_rows, page=scope["page"], page_size=scope["page_size"], total=total)


@frappe.whitelist()
def hours_by_user(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 50,
):
	scope = _timesheet_scope(from_date, to_date, company, page, page_size)
	if scope is None:
		fd, td, err = _parse_dates(from_date, to_date)
		return err
	if scope.get("empty"):
		return paginated([], page=scope["page"], page_size=scope["page_size"], total=0)

	rows = frappe.db.sql(
		f"""
		SELECT
			ts.employee AS employee,
			emp.user_id AS user,
			emp.employee_name AS employee_name,
			SUM(td.hours) AS hours,
			COUNT(*) AS entries,
			COUNT(DISTINCT COALESCE(td.project, ts.parent_project, '')) AS projects,
			COUNT(DISTINCT COALESCE(td.task, '')) AS tasks,
			COUNT(DISTINCT ts.name) AS timesheets
		FROM `tabTimesheet Detail` td
		INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		LEFT JOIN `tabEmployee` emp ON emp.name = ts.employee
		WHERE {scope["where"]}
		GROUP BY ts.employee, emp.user_id, emp.employee_name
		ORDER BY hours DESC
		""",
		scope["vals"],
		as_dict=True,
	)
	slice_rows, total = _paginate(rows, scope["page"], scope["page_size"])
	for r in slice_rows:
		r["hours"] = float(r.get("hours") or 0)
		r["entries"] = int(r.get("entries") or 0)
		r["projects"] = int(r.get("projects") or 0)
		r["tasks"] = int(r.get("tasks") or 0)
		r["timesheets"] = int(r.get("timesheets") or 0)
	return paginated(slice_rows, page=scope["page"], page_size=scope["page_size"], total=total)


@frappe.whitelist()
def hours_by_activity_type(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 50,
):
	scope = _timesheet_scope(from_date, to_date, company, page, page_size)
	if scope is None:
		fd, td, err = _parse_dates(from_date, to_date)
		return err
	if scope.get("empty"):
		return paginated([], page=scope["page"], page_size=scope["page_size"], total=0)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(td.activity_type, '') AS activity_type,
			SUM(td.hours) AS hours,
			COUNT(*) AS entries,
			COUNT(DISTINCT ts.employee) AS people
		FROM `tabTimesheet Detail` td
		INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		WHERE {scope["where"]}
		GROUP BY COALESCE(td.activity_type, '')
		ORDER BY hours DESC
		""",
		scope["vals"],
		as_dict=True,
	)
	slice_rows, total = _paginate(rows, scope["page"], scope["page_size"])
	for r in slice_rows:
		r["hours"] = float(r.get("hours") or 0)
		r["entries"] = int(r.get("entries") or 0)
		r["people"] = int(r.get("people") or 0)
		r["activity_type"] = r.get("activity_type") or None
	return paginated(slice_rows, page=scope["page"], page_size=scope["page_size"], total=total)


@frappe.whitelist()
def hours_by_task(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 50,
):
	scope = _timesheet_scope(from_date, to_date, company, page, page_size)
	if scope is None:
		fd, td, err = _parse_dates(from_date, to_date)
		return err
	if scope.get("empty"):
		return paginated([], page=scope["page"], page_size=scope["page_size"], total=0)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(td.task, '') AS task,
			COALESCE(td.project, ts.parent_project, '') AS project,
			COALESCE(td.activity_type, '') AS activity_type,
			ts.employee AS employee,
			emp.user_id AS user,
			emp.employee_name AS employee_name,
			SUM(td.hours) AS hours,
			COUNT(*) AS entries,
			COUNT(DISTINCT ts.name) AS timesheets
		FROM `tabTimesheet Detail` td
		INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		LEFT JOIN `tabEmployee` emp ON emp.name = ts.employee
		WHERE {scope["where"]}
		GROUP BY
			COALESCE(td.task, ''),
			COALESCE(td.project, ts.parent_project, ''),
			COALESCE(td.activity_type, ''),
			ts.employee,
			emp.user_id,
			emp.employee_name
		ORDER BY hours DESC
		""",
		scope["vals"],
		as_dict=True,
	)
	slice_rows, total = _paginate(rows, scope["page"], scope["page_size"])
	for r in slice_rows:
		r["hours"] = float(r.get("hours") or 0)
		r["entries"] = int(r.get("entries") or 0)
		r["timesheets"] = int(r.get("timesheets") or 0)
		r["task"] = r.get("task") or None
		r["project"] = r.get("project") or None
		r["activity_type"] = r.get("activity_type") or None
		if r["task"]:
			r["task_subject"] = frappe.db.get_value("Task", r["task"], "subject") or r["task"]
		else:
			r["task_subject"] = None
	return paginated(slice_rows, page=scope["page"], page_size=scope["page_size"], total=total)


@frappe.whitelist()
def hours_by_timesheet(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 50,
):
	"""One row per Timesheet (draft + submitted) in range."""
	scope = _timesheet_scope(from_date, to_date, company, page, page_size)
	if scope is None:
		fd, td, err = _parse_dates(from_date, to_date)
		return err
	if scope.get("empty"):
		return paginated([], page=scope["page"], page_size=scope["page_size"], total=0)

	rows = frappe.db.sql(
		f"""
		SELECT
			ts.name AS timesheet,
			ts.employee AS employee,
			emp.user_id AS user,
			emp.employee_name AS employee_name,
			ts.start_date AS start_date,
			ts.end_date AS end_date,
			ts.docstatus AS docstatus,
			ts.status AS status,
			COALESCE(ts.parent_project, '') AS project,
			SUM(td.hours) AS hours,
			COUNT(*) AS entries,
			COUNT(DISTINCT COALESCE(td.task, '')) AS tasks,
			COUNT(DISTINCT COALESCE(td.activity_type, '')) AS activity_types
		FROM `tabTimesheet Detail` td
		INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		LEFT JOIN `tabEmployee` emp ON emp.name = ts.employee
		WHERE {scope["where"]}
		GROUP BY
			ts.name, ts.employee, emp.user_id, emp.employee_name,
			ts.start_date, ts.end_date, ts.docstatus, ts.status, ts.parent_project
		ORDER BY ts.start_date DESC, hours DESC
		""",
		scope["vals"],
		as_dict=True,
	)
	slice_rows, total = _paginate(rows, scope["page"], scope["page_size"])
	for r in slice_rows:
		r["hours"] = float(r.get("hours") or 0)
		r["entries"] = int(r.get("entries") or 0)
		r["tasks"] = int(r.get("tasks") or 0)
		r["activity_types"] = int(r.get("activity_types") or 0)
		r["project"] = r.get("project") or None
		ds = int(r.get("docstatus") or 0)
		r["docstatus_label"] = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(ds, str(ds))
		if r.get("start_date"):
			r["start_date"] = str(r["start_date"])
		if r.get("end_date"):
			r["end_date"] = str(r["end_date"])
	return paginated(slice_rows, page=scope["page"], page_size=scope["page_size"], total=total)


@frappe.whitelist()
def hours_detail(
	from_date: str | None = None,
	to_date: str | None = None,
	company: str | None = None,
	page: int = 1,
	page_size: int = 100,
):
	"""Line-level ledger: user + timesheet + task + project + activity type."""
	scope = _timesheet_scope(from_date, to_date, company, page, page_size)
	if scope is None:
		fd, td, err = _parse_dates(from_date, to_date)
		return err
	if scope.get("empty"):
		return paginated([], page=scope["page"], page_size=scope["page_size"], total=0)

	rows = frappe.db.sql(
		f"""
		SELECT
			ts.name AS timesheet,
			ts.docstatus AS docstatus,
			ts.employee AS employee,
			emp.user_id AS user,
			emp.employee_name AS employee_name,
			COALESCE(td.project, ts.parent_project, '') AS project,
			COALESCE(td.task, '') AS task,
			COALESCE(td.activity_type, '') AS activity_type,
			td.from_time AS from_time,
			td.to_time AS to_time,
			td.hours AS hours,
			td.description AS description
		FROM `tabTimesheet Detail` td
		INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		LEFT JOIN `tabEmployee` emp ON emp.name = ts.employee
		WHERE {scope["where"]}
		ORDER BY td.from_time DESC
		""",
		scope["vals"],
		as_dict=True,
	)
	slice_rows, total = _paginate(rows, scope["page"], scope["page_size"])
	task_names = {r.get("task") for r in slice_rows if r.get("task")}
	subjects = {}
	if task_names:
		for t in frappe.get_all(
			"Task",
			filters={"name": ("in", list(task_names))},
			fields=["name", "subject"],
		):
			subjects[t.name] = t.subject
	for r in slice_rows:
		r["hours"] = float(r.get("hours") or 0)
		r["project"] = r.get("project") or None
		r["task"] = r.get("task") or None
		r["activity_type"] = r.get("activity_type") or None
		r["task_subject"] = subjects.get(r["task"]) if r["task"] else None
		ds = int(r.get("docstatus") or 0)
		r["docstatus_label"] = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(ds, str(ds))
		for key in ("from_time", "to_time"):
			if r.get(key):
				r[key] = str(r[key])
	return paginated(slice_rows, page=scope["page"], page_size=scope["page_size"], total=total)
