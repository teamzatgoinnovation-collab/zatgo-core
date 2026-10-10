"""Project list/create wrappers."""

from __future__ import annotations

import frappe
from frappe import _

from zatgo_core.tracker.api.response import fail, ok, paginated
from zatgo_core.tracker.permissions.capabilities import assert_can_manage_work, assert_is_top
from zatgo_core.tracker.permissions.hierarchy import get_company_for_user
from zatgo_core.tracker.services.assign import assign_project_member, parse_users
from zatgo_core.tracker.services.audit import log_event


@frappe.whitelist()
def list_projects(page: int = 1, page_size: int = 20, status: str | None = None):
	page = int(page or 1)
	page_size = min(int(page_size or 20), 100)
	filters: dict = {}
	company = get_company_for_user()
	if company:
		filters["company"] = company
	if status:
		filters["status"] = status
	total = frappe.db.count("Project", filters)
	rows = frappe.get_all(
		"Project",
		filters=filters,
		fields=["name", "project_name", "status", "company", "expected_start_date", "expected_end_date", "percent_complete", "modified"],
		order_by="modified desc",
		start=(page - 1) * page_size,
		page_length=page_size,
	)
	return paginated(rows, page=page, page_size=page_size, total=total)


@frappe.whitelist()
def get_project(name: str):
	if not name:
		return fail("missing_name", "Project name is required")
	doc = frappe.get_doc("Project", name)
	doc.check_permission("read")
	return ok(doc.as_dict())


@frappe.whitelist()
def create_project(project_name: str, company: str | None = None, notes: str | None = None):
	assert_can_manage_work()
	if not project_name:
		return fail("missing_name", "project_name is required")
	company = company or get_company_for_user()
	if not company:
		return fail("missing_company", "Company is required")
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"company": company,
			"notes": notes,
			"status": "Open",
		}
	)
	doc.insert()
	# add creator as member
	if frappe.session.user not in {r.user for r in doc.get("users") or []}:
		doc.append("users", {"user": frappe.session.user})
		doc.save()
	log_event("Project", doc.name, action="create")
	return ok(doc.as_dict())


@frappe.whitelist()
def add_member(project: str, user: str | None = None, users: str | None = None):
	targets = parse_users(users) or parse_users(user)
	if not project or not targets:
		return fail("bad_request", "project and user(s) required")
	for u in targets:
		assign_project_member(project, u)
	return ok({"project": project, "users": targets})


@frappe.whitelist()
def close_project(name: str):
	assert_is_top()
	if not name:
		return fail("bad_request", "name required")
	doc = frappe.get_doc("Project", name)
	prev = doc.status
	doc.status = "Completed"
	doc.save()
	log_event("Project", name, action="close", from_stage=prev, to_stage="Completed")
	return ok(doc.as_dict())
