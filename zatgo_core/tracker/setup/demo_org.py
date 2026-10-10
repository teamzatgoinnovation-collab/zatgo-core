"""Demo org seed: Top → Sub → Worker on Employee.reports_to."""

from __future__ import annotations

import frappe
from frappe import _

from zatgo_core.tracker.permissions.roles import TRACKER_ROLES, TRACKER_SUB, TRACKER_TOP, TRACKER_WORKER


DEMO_USERS = (
	{
		"email": "tracker.top@example.com",
		"full_name": "Tracker Top",
		"org_role": "Top",
		"frappe_role": TRACKER_TOP,
		"reports_to_email": None,
	},
	{
		"email": "tracker.sub@example.com",
		"full_name": "Tracker Sub",
		"org_role": "Sub",
		"frappe_role": TRACKER_SUB,
		"reports_to_email": "tracker.top@example.com",
	},
	{
		"email": "tracker.worker@example.com",
		"full_name": "Tracker Worker",
		"org_role": "Worker",
		"frappe_role": TRACKER_WORKER,
		"reports_to_email": "tracker.sub@example.com",
	},
)


def seed_demo_org(company: str | None = None) -> dict:
	"""Create 3 demo users/employees with Tracker roles and reports_to tree."""
	if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
		frappe.throw(_("Only System Manager can seed demo org."), frappe.PermissionError)

	company = company or frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		companies = frappe.get_all("Company", pluck="name", limit=1)
		company = companies[0] if companies else None
	if not company:
		frappe.throw(_("Create a Company first."))

	created = []
	# pass 1: users + employees without reports_to
	for row in DEMO_USERS:
		user = _ensure_user(row["email"], row["full_name"], row["frappe_role"])
		emp = _ensure_employee(user, row["full_name"], company, row["org_role"], reports_to=None)
		created.append({"user": user, "employee": emp, "org_role": row["org_role"]})

	# pass 2: wire reports_to
	email_to_emp = {r["email"]: frappe.db.get_value("Employee", {"user_id": r["email"]}, "name") for r in DEMO_USERS}
	for row in DEMO_USERS:
		if not row["reports_to_email"]:
			continue
		emp = email_to_emp.get(row["email"])
		mgr = email_to_emp.get(row["reports_to_email"])
		if emp and mgr:
			frappe.db.set_value("Employee", emp, "reports_to", mgr)

	frappe.db.commit()
	return {"company": company, "users": created}


def _ensure_user(email: str, full_name: str, role: str) -> str:
	if not frappe.db.exists("User", email):
		doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": full_name.split()[0],
				"last_name": " ".join(full_name.split()[1:]) or "Tracker",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		doc.insert(ignore_permissions=True)
		doc.new_password = "Tracker@123"
		doc.save(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	roles = {r.role for r in user.roles}
	for r in TRACKER_ROLES:
		if r == role and r not in roles:
			user.append_roles(r)
	if "Employee" not in roles and frappe.db.exists("Role", "Employee"):
		user.append_roles("Employee")
	user.save(ignore_permissions=True)
	return email


def _ensure_employee(user: str, full_name: str, company: str, org_role: str, reports_to: str | None) -> str:
	existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
	gender = _default_gender()
	if existing:
		doc = frappe.get_doc("Employee", existing)
	else:
		# ERPNext Employee often requires gender + date_of_birth
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
	if frappe.get_meta("Employee").has_field("tracker_org_role"):
		doc.tracker_org_role = org_role
	if reports_to:
		doc.reports_to = reports_to
	# backfill mandatory on existing incomplete employees
	if not doc.get("date_of_birth") and frappe.get_meta("Employee").has_field("date_of_birth"):
		doc.date_of_birth = "1990-01-15"
	if not doc.get("gender") and frappe.get_meta("Employee").has_field("gender"):
		doc.gender = gender
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	return doc.name


def _default_gender() -> str:
	meta = frappe.get_meta("Employee")
	gf = meta.get_field("gender")
	if gf and gf.fieldtype == "Link" and gf.options == "Gender":
		for name in ("Male", "Female", "Other"):
			if frappe.db.exists("Gender", name):
				return name
		try:
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
			return "Male"
		except Exception:
			g = frappe.db.get_value("Gender", {}, "name", order_by="creation asc")
			return g or "Male"
	return "Male"
