"""Demo work data: org + project/tasks/tickets + timesheets + live sessions."""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime, today

from zatgo_core.tracker.setup.demo_org import DEMO_USERS, seed_demo_org
from zatgo_core.tracker.doctype.tracker_settings.tracker_settings import get_default_activity_type

PROJECT_NAME = "Tracker Demo Project"
SESSION_DOCTYPE = "Tracker Activity Session"


def seed_demo_data(company: str | None = None) -> dict:
	"""Full pack so Workbench / Hours / Who-is-Running show results."""
	if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
		frappe.throw(_("Only System Manager can seed demo data."), frappe.PermissionError)

	# Assign-to may try to email; mute so seed works without Email Account
	frappe.flags.mute_emails = True
	org = seed_demo_org(company=company)
	company = org["company"]
	_ensure_activity_type("Execution")
	_ensure_tracker_settings(company)

	users = {r["email"]: r for r in DEMO_USERS}
	emp = {
		email: frappe.db.get_value("Employee", {"user_id": email}, "name") for email in users
	}
	worker = "tracker.worker@example.com"
	sub = "tracker.sub@example.com"
	top = "tracker.top@example.com"

	project = _ensure_project(company, [top, sub, worker])
	tasks = _ensure_tasks(company, project, worker, sub)
	tickets = _ensure_tickets(company, project, worker, sub)
	timesheets = _ensure_timesheets(company, emp, project, tasks)
	sessions = _ensure_sessions(company, project, tasks, emp, worker, sub)

	frappe.db.commit()
	return {
		"company": company,
		"org": org,
		"project": project,
		"tasks": tasks,
		"tickets": tickets,
		"timesheets": timesheets,
		"sessions": sessions,
		"login_hint": {
			"password": "Tracker@123",
			"users": [top, sub, worker],
		},
	}


def _ensure_activity_type(name: str) -> None:
	if not frappe.db.exists("DocType", "Activity Type"):
		return
	if frappe.db.exists("Activity Type", name):
		return
	try:
		frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(
			ignore_permissions=True
		)
	except Exception:
		pass


def _ensure_tracker_settings(company: str) -> None:
	if not frappe.db.exists("DocType", "Tracker Settings"):
		return
	doc = frappe.get_single("Tracker Settings")
	changed = False
	if not doc.default_company:
		doc.default_company = company
		changed = True
	if hasattr(doc, "default_activity_type") and not doc.default_activity_type:
		if frappe.db.exists("Activity Type", "Execution"):
			doc.default_activity_type = "Execution"
			changed = True
	if changed:
		doc.save(ignore_permissions=True)


def _ensure_project(company: str, members: list[str]) -> str:
	existing = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")
	if existing:
		name = existing
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": PROJECT_NAME,
				"company": company,
				"status": "Open",
				"expected_start_date": add_days(today(), -14),
				"expected_end_date": add_days(today(), 30),
			}
		)
		doc.insert(ignore_permissions=True)
		name = doc.name

	doc = frappe.get_doc("Project", name)
	have = {row.user for row in (doc.get("users") or [])}
	for u in members:
		if u not in have:
			doc.append("users", {"user": u})
	doc.save(ignore_permissions=True)
	return name


def _assign(doctype: str, name: str, user: str) -> None:
	from frappe.desk.form.assign_to import add as assign_add

	try:
		assign_add(
			{
				"assign_to": [user],
				"doctype": doctype,
				"name": name,
				"description": "Demo assign",
				"notify": 0,
			},
			ignore_permissions=True,
		)
	except Exception:
		# Fallback: ToDo only (no email)
		if not frappe.db.exists(
			"ToDo",
			{"reference_type": doctype, "reference_name": name, "allocated_to": user, "status": "Open"},
		):
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": user,
					"reference_type": doctype,
					"reference_name": name,
					"description": f"Demo assign {doctype} {name}",
					"status": "Open",
					"priority": "Medium",
				}
			).insert(ignore_permissions=True)


def _ensure_tasks(company: str, project: str, worker: str, sub: str) -> dict:
	"""Create parent + child tasks; assign worker/sub."""
	out = {}
	specs = [
		("TRK Demo — Design", None, sub, True),
		("TRK Demo — Wireframes", "TRK Demo — Design", worker, False),
		("TRK Demo — Build", None, worker, True),
		("TRK Demo — API hooks", "TRK Demo — Build", worker, False),
		("TRK Demo — QA", None, sub, False),
	]
	# first pass create without parent
	by_subject = {}
	for subject, _parent_subj, assignee, is_group in specs:
		name = frappe.db.get_value(
			"Task", {"subject": subject, "project": project}, "name"
		)
		if not name:
			doc = frappe.get_doc(
				{
					"doctype": "Task",
					"subject": subject,
					"project": project,
					"company": company,
					"status": "Open",
					"priority": "Medium",
					"is_group": 1 if is_group else 0,
					"exp_start_date": add_days(today(), -7),
					"exp_end_date": add_days(today(), 14),
				}
			)
			doc.insert(ignore_permissions=True)
			name = doc.name
			_assign("Task", name, assignee)
		by_subject[subject] = name
		out[subject] = name

	# wire parent_task
	for subject, parent_subj, _assignee, _ig in specs:
		if not parent_subj:
			continue
		child = by_subject.get(subject)
		parent = by_subject.get(parent_subj)
		if child and parent:
			frappe.db.set_value("Task", child, "parent_task", parent)
			frappe.db.set_value("Task", parent, "is_group", 1)

	return out


def _ensure_tickets(company: str, project: str, worker: str, sub: str) -> list[str]:
	names = []
	specs = [
		("TRK Demo — Login timeout on mobile", worker),
		("TRK Demo — Hours report empty state", sub),
	]
	for subject, assignee in specs:
		name = frappe.db.get_value("Issue", {"subject": subject, "project": project}, "name")
		if not name:
			doc = frappe.get_doc(
				{
					"doctype": "Issue",
					"subject": subject,
					"project": project,
					"company": company,
					"priority": "Medium",
					"status": "Open",
					"raised_by": "tracker.top@example.com",
					"description": "Seeded demo ticket for Tracker UI.",
				}
			)
			doc.insert(ignore_permissions=True)
			name = doc.name
			_assign("Issue", name, assignee)
		names.append(name)
	return names


def _ensure_timesheets(company: str, emp: dict, project: str, tasks: dict) -> list[str]:
	"""Create draft Timesheets with hours so Hours report has rows."""
	activity = get_default_activity_type() or "Execution"
	_ensure_activity_type(activity)
	created = []
	# worker: 3 days × ~2h on Build task; sub: 2 days × 1.5h on Design
	plan = [
		("tracker.worker@example.com", tasks.get("TRK Demo — Build"), 2.0, [1, 2, 3]),
		("tracker.sub@example.com", tasks.get("TRK Demo — Design"), 1.5, [2, 4]),
		("tracker.top@example.com", tasks.get("TRK Demo — QA"), 1.0, [1]),
	]
	for user, task, hours, day_offsets in plan:
		employee = emp.get(user)
		if not employee:
			continue
		for offset in day_offsets:
			day = add_days(today(), -offset)
			# idempotent marker in description
			marker = f"Tracker demo {user} {day}"
			exists = frappe.db.sql(
				"""
				SELECT td.parent FROM `tabTimesheet Detail` td
				WHERE td.description = %s LIMIT 1
				""",
				marker,
			)
			if exists:
				created.append(exists[0][0])
				continue
			from_time = get_datetime(f"{day} 09:00:00")
			to_time = from_time + timedelta(hours=hours)
			ts = frappe.get_doc(
				{
					"doctype": "Timesheet",
					"employee": employee,
					"company": company,
					"parent_project": project,
					"time_logs": [
						{
							"activity_type": activity,
							"from_time": from_time,
							"to_time": to_time,
							"hours": hours,
							"project": project,
							"task": task,
							"completed": 1,
							"description": marker,
						}
					],
				}
			)
			ts.insert(ignore_permissions=True)
			created.append(ts.name)
	return created


def _ensure_sessions(
	company: str,
	project: str,
	tasks: dict,
	emp: dict,
	worker: str,
	sub: str,
) -> list[dict]:
	"""One Running (worker) + one Paused (sub) for Who-is-Running / Workbench."""
	activity = get_default_activity_type() or "Execution"
	out = []
	now = now_datetime()

	# stop leftover demo running sessions for these users first (keep one each)
	specs = [
		{
			"user": worker,
			"task": tasks.get("TRK Demo — API hooks") or tasks.get("TRK Demo — Build"),
			"status": "Running",
			"started_on": now - timedelta(minutes=25),
			"duration_seconds": 0,
		},
		{
			"user": sub,
			"task": tasks.get("TRK Demo — Wireframes") or tasks.get("TRK Demo — Design"),
			"status": "Paused",
			"started_on": now - timedelta(hours=1),
			"paused_on": now - timedelta(minutes=10),
			"duration_seconds": 1800,
		},
	]
	for spec in specs:
		user = spec["user"]
		# close other active for user
		for name in frappe.get_all(
			SESSION_DOCTYPE,
			filters={"user": user, "status": ("in", ("Running", "Paused"))},
			pluck="name",
		):
			frappe.db.set_value(SESSION_DOCTYPE, name, "status", "Stopped")
			frappe.db.set_value(SESSION_DOCTYPE, name, "ended_on", now)
			frappe.db.set_value(SESSION_DOCTYPE, name, "docstatus", 0)

		doc = frappe.get_doc(
			{
				"doctype": SESSION_DOCTYPE,
				"user": user,
				"employee": emp.get(user),
				"company": company,
				"project": project,
				"task": spec.get("task"),
				"activity_type": activity,
				"status": spec["status"],
				"started_on": spec["started_on"],
				"paused_on": spec.get("paused_on"),
				"duration_seconds": spec.get("duration_seconds") or 0,
			}
		)
		doc.insert(ignore_permissions=True)
		out.append({"name": doc.name, "user": user, "status": doc.status})
	return out
