"""Comment-based Tracker audit trail ([tracker] prefix) + org activity feed."""

from __future__ import annotations

import re

import frappe
from frappe.utils import escape_html

from zatgo_core.tracker.permissions.capabilities import is_lead_or_above, is_system, is_top
from zatgo_core.tracker.permissions.hierarchy import get_company_for_user, get_subordinate_users

PREFIX = "[tracker]"

REF_DOCTYPES = (
	"Task",
	"Project",
	"Issue",
	"Timesheet",
	"Tracker Activity Session",
	"Employee",
)

ACTION_LABELS = {
	"start": "Started timer",
	"pause": "Paused timer",
	"resume": "Resumed timer",
	"stop": "Stopped timer",
	"create": "Created",
	"assign": "Assigned",
	"approve": "Approved",
	"rework": "Requested rework",
	"reject": "Rejected / rework",
	"submit_for_review": "Submitted for review",
	"set_in_progress": "Set in progress",
	"close": "Closed",
	"add_member": "Added project member",
	"submit_team": "Submitted team timesheets",
	"create_top": "Created Top",
	"assign_org": "Assigned org member",
	"update_org": "Updated org",
	"update": "Updated",
}


def log_event(
	doctype: str,
	name: str,
	*,
	action: str,
	from_stage: str | None = None,
	to_stage: str | None = None,
	note: str | None = None,
	extra: str | None = None,
) -> None:
	"""Append an Info comment on the document."""
	if not doctype or not name:
		return
	user = frappe.session.user
	parts = [PREFIX, f"action={action}", f"by={user}"]
	if from_stage:
		parts.append(f"from={from_stage}")
	if to_stage:
		parts.append(f"to={to_stage}")
	if note:
		parts.append(f"note={note}")
	if extra:
		parts.append(extra)
	content = " ".join(parts)
	try:
		doc = frappe.get_doc(doctype, name)
		doc.add_comment("Info", text=escape_html(content))
	except Exception:
		frappe.log_error(title=f"Tracker audit failed {doctype} {name}", message=frappe.get_traceback())


def list_for(doctype: str, name: str, limit: int = 50) -> list[dict]:
	if not doctype or not name:
		return []
	limit = min(int(limit or 50), 200)
	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"comment_type": "Info",
		},
		fields=["name", "content", "comment_email", "owner", "creation", "reference_doctype", "reference_name"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return [_enrich(row) for row in rows if _is_tracker_comment(row)]


def list_feed(
	*,
	limit: int = 100,
	user: str | None = None,
	action: str | None = None,
	scope: str | None = None,
) -> dict:
	"""Activity feed for Workbench — scoped by role.

	- Worker: own actions
	- Sub: self + subordinates
	- Top / System Manager: company tracker users (or all if no company)
	"""
	user = user or frappe.session.user
	limit = min(max(int(limit or 100), 1), 300)
	actors = _actors_for_viewer(user, scope=scope)

	# Pull recent tracker comments then filter (Comment has no fulltext index on content)
	rows = frappe.get_all(
		"Comment",
		filters={
			"comment_type": "Info",
			"reference_doctype": ("in", list(REF_DOCTYPES)),
		},
		fields=[
			"name",
			"content",
			"comment_email",
			"owner",
			"creation",
			"reference_doctype",
			"reference_name",
		],
		order_by="creation desc",
		limit_page_length=min(limit * 8, 1500),
	)

	items = []
	action_filter = (action or "").strip().lower() or None
	for row in rows:
		if not _is_tracker_comment(row):
			continue
		ev = _enrich(row)
		actor = ev.get("actor") or row.get("owner")
		if actors is not None and actor not in actors:
			continue
		if action_filter and (ev.get("action") or "").lower() != action_filter:
			continue
		items.append(ev)
		if len(items) >= limit:
			break

	return {
		"items": items,
		"scope_users": sorted(actors) if actors is not None else None,
		"viewer": user,
	}


def _actors_for_viewer(user: str, scope: str | None = None) -> set[str] | None:
	"""Return allowed actor emails, or None for unrestricted (System Manager company-wide uses set)."""
	scope = (scope or "").strip().lower() or "team"

	if is_system(user) or is_top(user):
		if scope == "mine":
			return {user}
		# company tracker users
		company = get_company_for_user(user)
		users = _company_tracker_users(company)
		users.add(user)
		if user == "Administrator":
			users.add("Administrator")
		return users

	if is_lead_or_above(user):
		if scope == "mine":
			return {user}
		subs = get_subordinate_users(user)
		subs.add(user)
		return subs

	# Worker (or anyone else): own only
	return {user}


def _company_tracker_users(company: str | None) -> set[str]:
	filters: dict = {"status": "Active", "user_id": ("is", "set")}
	if company:
		filters["company"] = company
	if frappe.get_meta("Employee").has_field("tracker_org_role"):
		# Prefer people with org role set; fall back to all company employees with user
		with_role = frappe.get_all(
			"Employee",
			filters={**filters, "tracker_org_role": ("in", ["Top", "Sub", "Worker"])},
			pluck="user_id",
		)
		if with_role:
			return {u for u in with_role if u}
	users = frappe.get_all("Employee", filters=filters, pluck="user_id")
	return {u for u in users if u}


def _is_tracker_comment(row: dict) -> bool:
	content = row.get("content") or ""
	plain = frappe.utils.strip_html(content) if content else ""
	return PREFIX in plain or PREFIX in content


def _enrich(row: dict) -> dict:
	content = row.get("content") or ""
	plain = frappe.utils.strip_html(content) if content else ""
	parsed = _parse(plain or content)
	action = parsed.get("action") or ""
	doctype = row.get("reference_doctype") or ""
	name = row.get("reference_name") or ""
	subject = _subject_for(doctype, name)
	return {
		"name": row.get("name"),
		"content": plain or content,
		"owner": row.get("owner"),
		"creation": row.get("creation"),
		"doctype": doctype,
		"docname": name,
		"subject": subject,
		"action": action,
		"action_label": ACTION_LABELS.get(action, action.replace("_", " ").title() if action else "Activity"),
		"actor": parsed.get("by") or row.get("owner"),
		"from_stage": parsed.get("from"),
		"to_stage": parsed.get("to"),
		"note": parsed.get("note"),
		"extra": parsed.get("extra"),
	}


def _parse(plain: str) -> dict:
	out: dict = {}
	if not plain:
		return out
	# action=foo by=user@x from=A to=B note=...
	for key in ("action", "by", "from", "to", "note"):
		m = re.search(rf"(?:^|\s){key}=([^\s]+(?:\s(?![a-z_]+=)[^\s]+)*)", plain)
		if m:
			out[key] = m.group(1).strip()
	# leftover extras like users=a,b
	extras = []
	for m in re.finditer(r"(?:^|\s)([a-z_]+)=([^\s]+)", plain):
		k = m.group(1)
		if k in ("action", "by", "from", "to", "note"):
			continue
		extras.append(f"{k}={m.group(2)}")
	if extras:
		out["extra"] = " ".join(extras)
	return out


def _subject_for(doctype: str, name: str) -> str:
	if not doctype or not name:
		return name or ""
	try:
		if doctype == "Task":
			return frappe.db.get_value("Task", name, "subject") or name
		if doctype == "Project":
			return frappe.db.get_value("Project", name, "project_name") or name
		if doctype == "Issue":
			return frappe.db.get_value("Issue", name, "subject") or name
		if doctype == "Employee":
			return frappe.db.get_value("Employee", name, "employee_name") or name
		if doctype == "Tracker Activity Session":
			task = frappe.db.get_value("Tracker Activity Session", name, "task")
			if task:
				subj = frappe.db.get_value("Task", task, "subject")
				return subj or task
			return name
	except Exception:
		pass
	return name
