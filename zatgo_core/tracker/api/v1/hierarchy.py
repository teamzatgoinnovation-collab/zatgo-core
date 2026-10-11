"""Hierarchy + assign-down-tree API + org setup."""

from __future__ import annotations

import frappe
from frappe import _

from zatgo_core.tracker.api.response import fail, ok
from zatgo_core.tracker.permissions.capabilities import (
	assert_can_manage_work,
	capability_payload,
	is_lead_or_above,
	is_system,
)
from zatgo_core.tracker.permissions.hierarchy import (
	can_assign_to,
	get_employee_for_user,
	get_org_role,
	get_subordinate_employees,
	get_subordinate_users,
)
from zatgo_core.tracker.permissions.roles import TRACKER_ROLES, TRACKER_SUB, TRACKER_TOP, TRACKER_WORKER
from zatgo_core.tracker.services.assign import assign_project_member, assign_task, parse_users
from zatgo_core.tracker.setup.demo_data import seed_demo_data
from zatgo_core.tracker.setup.demo_org import _default_gender, seed_demo_org


@frappe.whitelist()
def my_tree():
	"""Assignable people: self + subordinates (for assign pickers) + capability flags."""
	user = frappe.session.user
	emp = get_employee_for_user(user)
	subs = sorted(get_subordinate_users(user))
	people = []
	seen = set()
	for u in [user, *subs]:
		if not u or u in seen:
			continue
		seen.add(u)
		full_name = frappe.db.get_value("User", u, "full_name") or u
		people.append({"user": u, "full_name": full_name, "is_self": u == user})
	payload = {
		"user": user,
		"employee": emp,
		"org_role": get_org_role(emp),
		"subordinates": subs,
		"people": people,
	}
	payload.update(capability_payload(user))
	return ok(payload)


@frappe.whitelist()
def org_tree():
	"""Full active Employee tree for Org Setup (company-scoped)."""
	from zatgo_core.tracker.permissions.hierarchy import get_company_for_user

	company = get_company_for_user()
	filters: dict = {"status": "Active"}
	if company:
		filters["company"] = company
	fields = ["name", "employee_name", "user_id", "reports_to", "company"]
	if frappe.get_meta("Employee").has_field("tracker_org_role"):
		fields.append("tracker_org_role")
	if frappe.get_meta("Employee").has_field("branch"):
		fields.append("branch")
	rows = frappe.get_all("Employee", filters=filters, fields=fields, order_by="employee_name asc")
	# attach roles for users
	for row in rows:
		row["roles"] = []
		if row.get("user_id"):
			user_roles = set(frappe.get_roles(row.user_id))
			row["roles"] = [r for r in TRACKER_ROLES if r in user_roles]
	return ok({"company": company, "employees": rows})


@frappe.whitelist()
def create_top_member(
	email: str,
	full_name: str,
	company: str,
	branch: str | None = None,
):
	"""System Manager only: create User + Employee with Tracker Top."""
	if not is_system():
		frappe.throw(_("Only System Manager can create Top members."), frappe.PermissionError)
	if not email or not full_name or not company:
		return fail("bad_request", "email, full_name, and company required")

	result = _provision_member(
		email=email.strip(),
		full_name=full_name.strip(),
		company=company,
		frappe_role=TRACKER_TOP,
		org_role="Top",
		branch=branch,
		reports_to=None,
	)
	from zatgo_core.tracker.services.audit import log_event

	if result.get("employee"):
		log_event(
			"Employee",
			result["employee"],
			action="create_top",
			extra=f"user={result.get('user') or email}",
		)
	return ok(result)


@frappe.whitelist()
def assign_org_member(
	email: str,
	full_name: str,
	company: str,
	role: str,
	branch: str | None = None,
	reports_to: str | None = None,
):
	"""Top/Sub: create Sub or Worker under the org tree."""
	if not is_lead_or_above():
		frappe.throw(_("Only Team Leads and Managers can assign org members."), frappe.PermissionError)
	if not email or not full_name or not company or not role:
		return fail("bad_request", "email, full_name, company, and role required")

	role = (role or "").strip()
	if role not in ("Sub", "Worker"):
		return fail("bad_request", 'role must be "Sub" or "Worker"')

	# Sub cannot assign Top (already blocked by role allow-list)
	frappe_role = TRACKER_SUB if role == "Sub" else TRACKER_WORKER
	creator_emp = get_employee_for_user()
	if reports_to is None:
		reports_to = creator_emp

	# Sub may only place people under themselves (or within their tree)
	roles = set(frappe.get_roles())
	if TRACKER_SUB in roles and TRACKER_TOP not in roles and not is_system():
		if not creator_emp:
			frappe.throw(_("Your Employee record is required to assign org members."), frappe.PermissionError)
		if reports_to and reports_to != creator_emp:
			subs = get_subordinate_employees(creator_emp)
			if reports_to not in subs and reports_to != creator_emp:
				frappe.throw(
					_("You can only assign members under your subordinate tree."),
					frappe.PermissionError,
				)
		# Nor may a Sub take over someone already in the system: an existing
		# user's Employee would otherwise be moved under them (company and
		# reports_to overwritten, tracker roles reset) -- only people already
		# in their tree, and only within their own company.
		own_company = frappe.db.get_value("Employee", creator_emp, "company")
		if company != own_company:
			frappe.throw(_("You can only assign members in your own company."), frappe.PermissionError)
		existing_user = frappe.db.get_value("User", {"name": email.strip()}, "name") or frappe.db.get_value(
			"User", {"email": email.strip()}, "name"
		)
		if existing_user:
			existing_emp = frappe.db.get_value("Employee", {"user_id": existing_user}, "name")
			if existing_emp and existing_emp not in get_subordinate_employees(creator_emp):
				frappe.throw(
					_("{0} already belongs to someone outside your team.").format(email),
					frappe.PermissionError,
				)

	result = _provision_member(
		email=email.strip(),
		full_name=full_name.strip(),
		company=company,
		frappe_role=frappe_role,
		org_role=role,
		branch=branch,
		reports_to=reports_to,
	)
	from zatgo_core.tracker.services.audit import log_event

	if result.get("employee"):
		log_event(
			"Employee",
			result["employee"],
			action="assign_org",
			extra=f"user={result.get('user') or email} role={role}",
		)
	return ok(result)


@frappe.whitelist()
def update_employee_org(
	employee: str,
	tracker_org_role: str | None = None,
	reports_to: str | None = None,
	tracker_role: str | None = None,
):
	"""Set org role / reports_to / Frappe Tracker role on Employee+User."""
	if not employee:
		return fail("bad_request", "employee required")

	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	full_access = is_system(user) or TRACKER_TOP in roles

	if not full_access:
		if TRACKER_SUB not in roles:
			frappe.throw(_("Not permitted to update org setup."), frappe.PermissionError)
		my_emp = get_employee_for_user(user)
		if not my_emp:
			frappe.throw(_("Not permitted to update org setup."), frappe.PermissionError)
		subs = get_subordinate_employees(my_emp)
		if employee not in subs:
			frappe.throw(
				_("You can only update employees in your subordinate tree."),
				frappe.PermissionError,
			)
		# Sub cannot promote to Top
		if tracker_org_role == "Top" or tracker_role == TRACKER_TOP:
			frappe.throw(_("Team Leads cannot promote to Top."), frappe.PermissionError)

	doc = frappe.get_doc("Employee", employee)
	if tracker_org_role is not None and frappe.get_meta("Employee").has_field("tracker_org_role"):
		doc.tracker_org_role = tracker_org_role or None
	if reports_to is not None:
		doc.reports_to = reports_to or None
	doc.save(ignore_permissions=True)

	if tracker_role is not None and doc.user_id:
		user_doc = frappe.get_doc("User", doc.user_id)
		# remove other Tracker roles then add selected (empty clears all)
		user_doc.roles = [r for r in user_doc.roles if r.role not in TRACKER_ROLES]
		if tracker_role in TRACKER_ROLES:
			user_doc.append_roles(tracker_role)
		user_doc.save(ignore_permissions=True)

	from zatgo_core.tracker.services.audit import log_event

	log_event(
		"Employee",
		employee,
		action="update_org",
		extra=f"role={tracker_org_role or ''} reports_to={reports_to or ''}",
	)

	return ok(frappe.get_doc("Employee", employee).as_dict())


@frappe.whitelist()
def seed_demo(company: str | None = None):
	"""Org tree only (Top / Sub / Worker)."""
	return ok(seed_demo_org(company=company))


@frappe.whitelist()
def seed_demo_work(company: str | None = None):
	"""Full demo: org + project/tasks/tickets + timesheets + live sessions."""
	return ok(seed_demo_data(company=company))


@frappe.whitelist()
def can_assign(assignee: str):
	return ok({"assignee": assignee, "allowed": can_assign_to(frappe.session.user, assignee)})


@frappe.whitelist()
def assign(doctype: str, name: str, users: str | None = None, user: str | None = None):
	assert_can_manage_work()
	targets = parse_users(users) or parse_users(user)
	if not doctype or not name or not targets:
		return fail("bad_request", "doctype, name, and user(s) required")
	if doctype == "Task":
		assign_task(name, targets)
	elif doctype == "Project":
		for u in targets:
			assign_project_member(name, u)
	elif doctype == "Issue":
		from frappe.desk.form.assign_to import add as assign_add
		from zatgo_core.tracker.permissions.hierarchy import assert_can_assign
		from zatgo_core.tracker.services.audit import log_event
		from zatgo_core.tracker.services.notify import notify_assigned

		for u in targets:
			assert_can_assign(frappe.session.user, u)
			assign_add(
				{
					"assign_to": [u],
					"doctype": "Issue",
					"name": name,
					"description": "Assigned via Tracker",
				}
			)
		log_event("Issue", name, action="assign", extra=f"users={','.join(targets)}")
		notify_assigned(doctype="Issue", name=name, users=targets)
	else:
		return fail("unsupported", f"Cannot assign {doctype}")
	return ok({"doctype": doctype, "name": name, "users": targets})


def _provision_member(
	*,
	email: str,
	full_name: str,
	company: str,
	frappe_role: str,
	org_role: str,
	branch: str | None,
	reports_to: str | None,
) -> dict:
	"""Create/update User + Employee; return temporary_password when user is new."""
	temporary_password = None
	created_user = False

	if not frappe.db.exists("User", email):
		parts = full_name.split()
		first = parts[0]
		last = " ".join(parts[1:]) or "User"
		temporary_password = frappe.generate_hash(length=12)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first,
				"last_name": last,
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
		user.new_password = temporary_password
		user.save(ignore_permissions=True)
		created_user = True
	else:
		user = frappe.get_doc("User", email)

	# one Tracker org role at a time
	user.roles = [r for r in user.roles if r.role not in TRACKER_ROLES]
	user.append_roles(frappe_role)
	if "Employee" not in {r.role for r in user.roles} and frappe.db.exists("Role", "Employee"):
		user.append_roles("Employee")
	user.save(ignore_permissions=True)

	emp_name = _ensure_employee_record(
		user=email,
		full_name=full_name,
		company=company,
		org_role=org_role,
		reports_to=reports_to,
		branch=branch,
	)
	frappe.db.commit()
	return {
		"user": email,
		"employee": emp_name,
		"org_role": org_role,
		"frappe_role": frappe_role,
		"temporary_password": temporary_password,
		"created_user": created_user,
	}


def _ensure_employee_record(
	*,
	user: str,
	full_name: str,
	company: str,
	org_role: str,
	reports_to: str | None,
	branch: str | None,
) -> str:
	existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
	gender = _default_gender()
	meta = frappe.get_meta("Employee")
	if existing:
		doc = frappe.get_doc("Employee", existing)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Employee",
				"employee_name": full_name,
				"first_name": full_name.split()[0],
				"company": company,
				"status": "Active",
				"user_id": user,
				"date_of_joining": frappe.utils.today(),
				"date_of_birth": "1990-01-15",
				"gender": gender,
			}
		)

	doc.company = company
	if meta.has_field("tracker_org_role"):
		doc.tracker_org_role = org_role
	if reports_to is not None:
		doc.reports_to = reports_to or None
	if branch and meta.has_field("branch"):
		doc.branch = branch
	if not doc.get("date_of_birth") and meta.has_field("date_of_birth"):
		doc.date_of_birth = "1990-01-15"
	if not doc.get("gender") and meta.has_field("gender"):
		doc.gender = gender

	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	return doc.name
