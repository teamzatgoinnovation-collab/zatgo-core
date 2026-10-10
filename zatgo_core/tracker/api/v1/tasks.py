"""Task list/create + lifecycle (writes ERPNext Task.status)."""

from __future__ import annotations

import frappe

from zatgo_core.tracker.api.response import fail, ok, paginated
from zatgo_core.tracker.permissions.capabilities import assert_can_manage_work
from zatgo_core.tracker.permissions.hierarchy import get_company_for_user
from zatgo_core.tracker.services.assign import assign_task, parse_users
from zatgo_core.tracker.services.audit import log_event
from zatgo_core.tracker.services.review import (
	STAGE_DRAFT,
	approve_task as review_approve,
	enrich_task_row,
	get_task_stage,
	request_rework as review_request_rework,
	set_in_progress,
	submit_for_review as review_submit_for_review,
	team_review_filters,
)


@frappe.whitelist()
def list_tasks(
	page: int = 1,
	page_size: int = 50,
	project: str | None = None,
	status: str | None = None,
	stage: str | None = None,
	mine: int = 0,
	team: int = 0,
	parent_task: str | None = None,
	tree: int = 0,
	review_queue: int = 0,
):
	from zatgo_core.tracker.permissions.hierarchy import get_subordinate_users

	page = int(page or 1)
	page_size = min(int(page_size or 50), 200)

	if int(review_queue or 0):
		filters, or_filters = team_review_filters()
	else:
		filters: dict = {}
		company = get_company_for_user()
		if company:
			filters["company"] = company
		if project:
			filters["project"] = project
		if status:
			filters["status"] = status
		if parent_task:
			filters["parent_task"] = parent_task

		or_filters = None
		if int(mine or 0) and int(team or 0):
			users = {frappe.session.user} | get_subordinate_users()
			or_filters = [["_assign", "like", f"%{u}%"] for u in users]
		elif int(mine or 0):
			filters["_assign"] = ("like", f"%{frappe.session.user}%")
		elif int(team or 0):
			users = get_subordinate_users()
			if not users:
				return paginated([], page=page, page_size=page_size, total=0)
			or_filters = [["_assign", "like", f"%{u}%"] for u in users]

		if stage == "Ready for Review":
			filters["status"] = "Pending Review"
		elif stage == "In Progress":
			filters["status"] = "Working"
		elif stage == "Completed":
			filters["status"] = "Completed"
		elif stage in ("Draft", "Assigned"):
			filters["status"] = "Open"

	total = len(
		frappe.get_all(
			"Task",
			filters=filters,
			or_filters=or_filters,
			pluck="name",
		)
	)
	rows = frappe.get_all(
		"Task",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"subject",
			"status",
			"priority",
			"project",
			"parent_task",
			"is_group",
			"exp_start_date",
			"exp_end_date",
			"_assign",
			"modified",
		],
		order_by="modified desc",
		start=(page - 1) * page_size,
		page_length=page_size,
	)
	enriched = [enrich_task_row(r) for r in rows]
	if stage == "Draft":
		enriched = [r for r in enriched if r.get("stage") == STAGE_DRAFT]
	elif stage == "Assigned":
		enriched = [r for r in enriched if r.get("stage") == "Assigned"]
	return paginated(enriched, page=page, page_size=page_size, total=total)


@frappe.whitelist()
def get_task(name: str):
	if not name:
		return fail("missing_name", "Task name is required")
	doc = frappe.get_doc("Task", name)
	doc.check_permission("read")
	children = frappe.get_all(
		"Task",
		filters={"parent_task": name},
		fields=["name", "subject", "status", "priority", "_assign"],
		order_by="creation asc",
	)
	data = enrich_task_row(doc.as_dict())
	data["subtasks"] = [enrich_task_row(c) for c in children]
	data["stage"] = get_task_stage(doc)
	return ok(data)


@frappe.whitelist()
def create_task(
	subject: str,
	project: str | None = None,
	parent_task: str | None = None,
	priority: str | None = None,
	description: str | None = None,
	assign_to: str | None = None,
):
	assert_can_manage_work()
	if not subject:
		return fail("missing_subject", "subject is required")
	company = None
	if project:
		company = frappe.db.get_value("Project", project, "company")
	company = company or get_company_for_user()
	doc = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"project": project,
			"parent_task": parent_task,
			"priority": priority or "Medium",
			"description": description,
			"company": company,
			"status": "Open",
			"is_group": 1 if not parent_task else 0,
		}
	)
	doc.insert()
	users = parse_users(assign_to)
	if users:
		assign_task(doc.name, users)
	else:
		log_event("Task", doc.name, action="create", to_stage=STAGE_DRAFT)
	return ok(enrich_task_row(frappe.get_doc("Task", doc.name).as_dict()))


@frappe.whitelist()
def update_status(name: str, status: str):
	"""Deprecated raw status write — route through lifecycle methods."""
	if not name or not status:
		return fail("bad_request", "name and status required")
	mapping = {
		"Working": "set_progress",
		"Pending Review": "submit_for_review",
		"Completed": "approve",
	}
	if status == "Working":
		return ok(set_in_progress(name))
	if status == "Pending Review":
		return ok(review_submit_for_review(name))
	if status == "Completed":
		return ok(review_approve(name))
	return fail(
		"use_lifecycle",
		f"Use lifecycle APIs instead of raw status={status}. Allowed via mapping: {mapping}",
	)


@frappe.whitelist()
def set_progress(name: str):
	"""Open/Assigned → Working."""
	if not name:
		return fail("bad_request", "name required")
	return ok(set_in_progress(name))


@frappe.whitelist()
def submit_for_review(name: str, note: str | None = None):
	if not name:
		return fail("bad_request", "name required")
	return ok(review_submit_for_review(name, note=note))


@frappe.whitelist()
def approve(name: str, note: str | None = None):
	if not name:
		return fail("bad_request", "name required")
	return ok(review_approve(name, note=note))


@frappe.whitelist()
def request_rework(name: str, note: str):
	if not name:
		return fail("bad_request", "name required")
	if not (note or "").strip():
		return fail("bad_request", "note required")
	return ok(review_request_rework(name, note=note))
