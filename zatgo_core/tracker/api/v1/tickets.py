"""Issue (ticket) wrappers."""

from __future__ import annotations

import frappe

from frappe.desk.form.assign_to import add as assign_add

from zatgo_core.tracker.api.response import fail, ok, paginated
from zatgo_core.tracker.permissions.capabilities import assert_can_manage_work
from zatgo_core.tracker.permissions.hierarchy import assert_can_assign, get_company_for_user
from zatgo_core.tracker.services.assign import parse_users
from zatgo_core.tracker.services.audit import log_event


@frappe.whitelist()
def list_tickets(
	page: int = 1,
	page_size: int = 50,
	project: str | None = None,
	status: str | None = None,
	mine: int = 0,
	team: int = 0,
):
	from zatgo_core.tracker.permissions.hierarchy import get_subordinate_users

	page = int(page or 1)
	page_size = min(int(page_size or 50), 200)
	filters: dict = {}
	company = get_company_for_user()
	if company:
		filters["company"] = company
	if project:
		filters["project"] = project
	if status:
		filters["status"] = status

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

	total = len(
		frappe.get_all(
			"Issue",
			filters=filters,
			or_filters=or_filters,
			pluck="name",
		)
	)
	rows = frappe.get_all(
		"Issue",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "subject", "status", "priority", "project", "raised_by", "modified", "_assign"],
		order_by="modified desc",
		start=(page - 1) * page_size,
		page_length=page_size,
	)
	return paginated(rows, page=page, page_size=page_size, total=total)


@frappe.whitelist()
def get_ticket(name: str):
	if not name:
		return fail("missing_name", "Issue name is required")
	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")
	return ok(doc.as_dict())


@frappe.whitelist()
def create_ticket(
	subject: str,
	project: str | None = None,
	description: str | None = None,
	priority: str | None = None,
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
			"doctype": "Issue",
			"subject": subject,
			"project": project,
			"description": description,
			"priority": priority or "Medium",
			"company": company,
			"raised_by": frappe.session.user,
		}
	)
	doc.insert()
	from zatgo_core.tracker.services.notify import notify_assigned

	assigned = parse_users(assign_to)
	for user in assigned:
		assert_can_assign(frappe.session.user, user)
		assign_add(
			{
				"assign_to": [user],
				"doctype": "Issue",
				"name": doc.name,
				"description": "Ticket assigned via Tracker",
			}
		)
	if assigned:
		notify_assigned(doctype="Issue", name=doc.name, users=assigned)
		log_event("Issue", doc.name, action="assign", extra=f"users={','.join(assigned)}")
	else:
		log_event("Issue", doc.name, action="create")
	return ok(frappe.get_doc("Issue", doc.name).as_dict())


@frappe.whitelist()
def assign(name: str, users: str | None = None, user: str | None = None):
	from zatgo_core.tracker.services.notify import notify_assigned

	assert_can_manage_work()
	targets = parse_users(users) or parse_users(user)
	if not name or not targets:
		return fail("bad_request", "name and user(s) required")
	for u in targets:
		assert_can_assign(frappe.session.user, u)
		assign_add(
			{
				"assign_to": [u],
				"doctype": "Issue",
				"name": name,
				"description": "Ticket assigned via Tracker",
			}
		)
	notify_assigned(doctype="Issue", name=name, users=targets)
	log_event("Issue", name, action="assign", extra=f"users={','.join(targets)}")
	return ok({"issue": name, "users": targets})
