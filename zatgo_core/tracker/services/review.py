"""Task lifecycle: Draft → Assigned → In Progress → Ready for Review → Completed / Rework."""

from __future__ import annotations

import json

import frappe
from frappe import _

from zatgo_core.tracker.permissions.capabilities import assert_can_review, is_lead_or_above, is_system
from zatgo_core.tracker.permissions.hierarchy import can_assign_to, get_subordinate_users
from zatgo_core.tracker.permissions.roles import TRACKER_TOP
from zatgo_core.tracker.services.audit import log_event

STAGE_DRAFT = "Draft"
STAGE_ASSIGNED = "Assigned"
STAGE_IN_PROGRESS = "In Progress"
STAGE_READY = "Ready for Review"
STAGE_COMPLETED = "Completed"


def _assignees(doc) -> list[str]:
	raw = doc.get("_assign") if hasattr(doc, "get") else getattr(doc, "_assign", None)
	if not raw:
		# refresh from DB
		name = doc.get("name") if hasattr(doc, "get") else getattr(doc, "name", None)
		if name:
			raw = frappe.db.get_value("Task", name, "_assign")
	if not raw:
		return []
	if isinstance(raw, list):
		return [str(u) for u in raw]
	try:
		parsed = json.loads(raw)
		if isinstance(parsed, list):
			return [str(u) for u in parsed]
	except Exception:
		pass
	return []


def get_task_stage(doc) -> str:
	"""Product stage from ERPNext Task status + assignees."""
	status = (doc.get("status") if hasattr(doc, "get") else getattr(doc, "status", None)) or "Open"
	if status == "Completed":
		return STAGE_COMPLETED
	if status == "Pending Review":
		return STAGE_READY
	if status == "Working":
		return STAGE_IN_PROGRESS
	# Open / other → Draft or Assigned by assignees
	if _assignees(doc):
		return STAGE_ASSIGNED
	return STAGE_DRAFT


def enrich_task_row(row: dict) -> dict:
	row = dict(row)
	row["stage"] = get_task_stage(row)
	row["assignees"] = _assignees(row)
	return row


def _is_assignee(doc, user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user in _assignees(doc)


def assert_is_assignee(doc, user: str | None = None) -> None:
	"""Only people on Task._assign may execute the task (start / submit)."""
	user = user or frappe.session.user
	if is_system(user):
		return
	if not _is_assignee(doc, user):
		frappe.throw(
			_("Only an assigned worker can work on this task."),
			frappe.PermissionError,
		)


def _can_review_task(doc, user: str | None = None) -> bool:
	"""Sub/Top above any assignee, or System Manager / Top with company scope."""
	user = user or frappe.session.user
	if is_system(user):
		return True
	assert_can_review(user)
	assignees = _assignees(doc)
	if not assignees:
		# unassigned Pending Review — lead may still act
		return is_lead_or_above(user)
	for a in assignees:
		if a == user:
			continue
		if can_assign_to(user, a):
			return True
	# Top reviewing own company work where assignee is self is odd; allow Top always
	from zatgo_core.tracker.permissions.capabilities import is_top

	return is_top(user)


def set_in_progress(task: str, user: str | None = None) -> dict:
	user = user or frappe.session.user
	doc = frappe.get_doc("Task", task)
	stage = get_task_stage(doc)
	if stage not in (STAGE_ASSIGNED, STAGE_IN_PROGRESS):
		frappe.throw(_("Task must be Assigned before starting work."), frappe.ValidationError)
	assert_is_assignee(doc, user)
	if doc.status == "Working":
		return enrich_task_row(doc.as_dict())
	prev = get_task_stage(doc)
	doc.status = "Working"
	doc.save(ignore_permissions=True)
	log_event("Task", doc.name, action="set_in_progress", from_stage=prev, to_stage=STAGE_IN_PROGRESS)
	return enrich_task_row(doc.as_dict())


def submit_for_review(task: str, note: str | None = None, user: str | None = None) -> dict:
	user = user or frappe.session.user
	doc = frappe.get_doc("Task", task)
	stage = get_task_stage(doc)
	if stage != STAGE_IN_PROGRESS:
		frappe.throw(_("Only In Progress tasks can be submitted for review."), frappe.ValidationError)
	assert_is_assignee(doc, user)
	prev = stage
	doc.status = "Pending Review"
	doc.save(ignore_permissions=True)
	log_event(
		"Task",
		doc.name,
		action="submit_for_review",
		from_stage=prev,
		to_stage=STAGE_READY,
		note=note,
	)
	return enrich_task_row(doc.as_dict())


def approve_task(task: str, note: str | None = None, user: str | None = None) -> dict:
	user = user or frappe.session.user
	doc = frappe.get_doc("Task", task)
	if get_task_stage(doc) != STAGE_READY:
		frappe.throw(_("Only Ready for Review tasks can be approved."), frappe.ValidationError)
	if not _can_review_task(doc, user):
		frappe.throw(_("You cannot approve this task."), frappe.PermissionError)
	prev = STAGE_READY
	doc.status = "Completed"
	doc.save(ignore_permissions=True)
	log_event(
		"Task",
		doc.name,
		action="approve",
		from_stage=prev,
		to_stage=STAGE_COMPLETED,
		note=note,
	)
	return enrich_task_row(doc.as_dict())


def request_rework(task: str, note: str, user: str | None = None) -> dict:
	user = user or frappe.session.user
	if not (note or "").strip():
		frappe.throw(_("A rework note is required."), frappe.ValidationError)
	doc = frappe.get_doc("Task", task)
	if get_task_stage(doc) != STAGE_READY:
		frappe.throw(_("Only Ready for Review tasks can be sent for rework."), frappe.ValidationError)
	if not _can_review_task(doc, user):
		frappe.throw(_("You cannot request rework on this task."), frappe.PermissionError)
	prev = STAGE_READY
	doc.status = "Working"
	doc.save(ignore_permissions=True)
	log_event(
		"Task",
		doc.name,
		action="rework",
		from_stage=prev,
		to_stage=STAGE_IN_PROGRESS,
		note=note.strip(),
	)
	return enrich_task_row(doc.as_dict())


def mark_working_on_start(task: str, user: str | None = None) -> None:
	"""Called from activity start: Assigned → In Progress; only assignees may start."""
	user = user or frappe.session.user
	if not task:
		return
	doc = frappe.get_doc("Task", task)
	assert_is_assignee(doc, user)
	stage = get_task_stage(doc)
	if stage == STAGE_DRAFT:
		frappe.throw(_("Assign this task before starting activity."), frappe.ValidationError)
	if stage == STAGE_COMPLETED:
		frappe.throw(_("Cannot start activity on a Completed task."), frappe.ValidationError)
	if stage == STAGE_READY:
		frappe.throw(_("Task is Ready for Review. Wait for approval or rework."), frappe.ValidationError)
	if stage == STAGE_ASSIGNED:
		set_in_progress(task, user=user)


def team_review_filters(user: str | None = None) -> tuple[dict, list | None]:
	"""Filters for Pending Review tasks visible to leads (team assignees)."""
	user = user or frappe.session.user
	filters: dict = {"status": "Pending Review"}
	from zatgo_core.tracker.permissions.hierarchy import get_company_for_user

	company = get_company_for_user(user)
	if company:
		filters["company"] = company
	if is_system(user) or (
		is_lead_or_above(user) and TRACKER_TOP in frappe.get_roles(user)
	):
		return filters, None
	users = get_subordinate_users(user) | {user}
	or_filters = [["_assign", "like", f"%{u}%"] for u in users]
	return filters, or_filters
