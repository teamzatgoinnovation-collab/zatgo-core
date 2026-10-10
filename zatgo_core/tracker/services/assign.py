"""Assignment helpers with down-tree validation."""

from __future__ import annotations

import json

import frappe
from frappe.desk.form.assign_to import add as assign_add

from zatgo_core.tracker.permissions.capabilities import assert_can_manage_work
from zatgo_core.tracker.permissions.hierarchy import assert_can_assign
from zatgo_core.tracker.services.audit import log_event
from zatgo_core.tracker.services.review import STAGE_ASSIGNED, STAGE_DRAFT, get_task_stage


def assign_task(task: str, users: list[str], assigner: str | None = None) -> None:
	from zatgo_core.tracker.services.notify import notify_assigned

	assigner = assigner or frappe.session.user
	assert_can_manage_work(assigner)
	prev = get_task_stage(frappe.get_doc("Task", task))
	for user in users:
		assert_can_assign(assigner, user)
		assign_add(
			{
				"assign_to": [user],
				"doctype": "Task",
				"name": task,
				"description": f"Assigned via Tracker by {assigner}",
			}
		)
	log_event(
		"Task",
		task,
		action="assign",
		from_stage=prev,
		to_stage=STAGE_ASSIGNED if prev == STAGE_DRAFT else prev,
		extra=f"users={','.join(users)}",
	)
	notify_assigned(doctype="Task", name=task, users=users, assigner=assigner)


def assign_project_member(project: str, user: str, assigner: str | None = None) -> None:
	assigner = assigner or frappe.session.user
	assert_can_manage_work(assigner)
	assert_can_assign(assigner, user)
	doc = frappe.get_doc("Project", project)
	existing = {row.user for row in doc.get("users") or []}
	if user not in existing:
		doc.append("users", {"user": user})
		doc.save(ignore_permissions=True)
		log_event("Project", project, action="add_member", extra=f"user={user}")


def parse_users(value) -> list[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [str(v) for v in value]
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []
		if value.startswith("["):
			return [str(v) for v in json.loads(value)]
		return [u.strip() for u in value.split(",") if u.strip()]
	return [str(value)]
