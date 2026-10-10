"""Setup for Tracker (formerly the tracker app) — run by
services/bundled_apps.py where ZG System Settings -> Enable Tracker is on,
never on other sites (it adds an Employee custom field and role
permissions on Project / Task / Issue / Timesheet). Desk entries are tagged
app "zatgo_core" and found by the sidebar they link to, never by app."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from zatgo_core.tracker.permissions.roles import ensure_role_permissions, ensure_roles

SIDEBAR_ITEMS = [
	{"label": "Workbench", "link_type": "Page", "link_to": "tracker-workbench", "type": "Link", "icon": "list"},
	{"label": "Hours", "link_type": "Page", "link_to": "tracker-hours", "type": "Link", "icon": "chart"},
	{"label": "Org Setup", "link_type": "Page", "link_to": "tracker-org", "type": "Link", "icon": "organization"},
	{"label": "Project", "link_type": "DocType", "link_to": "Project", "type": "Link", "icon": "project"},
	{"label": "Task", "link_type": "DocType", "link_to": "Task", "type": "Link", "icon": "list-checks"},
	{"label": "Issue", "link_type": "DocType", "link_to": "Issue", "type": "Link", "icon": "ticket"},
	{"label": "Employee", "link_type": "DocType", "link_to": "Employee", "type": "Link", "icon": "users"},
	{
		"label": "Activity Session",
		"link_type": "DocType",
		"link_to": "Tracker Activity Session",
		"type": "Link",
		"icon": "timer",
	},
	{
		"label": "Settings",
		"link_type": "DocType",
		"link_to": "Tracker Settings",
		"type": "Link",
		"icon": "setting",
	},
]


def _sidebar_item_exists(item: dict) -> bool:
	link_type = item.get("link_type")
	link_to = item.get("link_to")
	if not link_to:
		return False
	if link_type == "Page":
		return bool(frappe.db.exists("Page", link_to))
	if link_type == "DocType":
		return bool(frappe.db.exists("DocType", link_to))
	return True


def _safe_sidebar_items() -> list[dict]:
	"""Only link to Page/DocType rows that already exist (avoids install-order LinkValidationError)."""
	return [item for item in SIDEBAR_ITEMS if _sidebar_item_exists(item)]


def _save_ignore_links(doc) -> None:
	doc.flags.ignore_links = True
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)


def _sidebar_items_match(existing_items, expected_items: list[dict]) -> bool:
	if len(existing_items) != len(expected_items):
		return False
	for expected, row in zip(expected_items, existing_items):
		if (
			row.label,
			row.link_to,
			row.link_type,
			row.type,
		) != (
			expected["label"],
			expected["link_to"],
			expected["link_type"],
			expected["type"],
		):
			return False
	return True


def _sync_sidebar_items(sidebar) -> bool:
	"""Replace sidebar rows when labels/links drift from SIDEBAR_ITEMS."""
	expected = _safe_sidebar_items()
	if _sidebar_items_match(sidebar.items, expected):
		return False
	sidebar.items = []
	for item in expected:
		sidebar.append("items", item)
	return True


SIDEBAR_NAMES = ("Tracker", "Task Management")


def bootstrap() -> None:
	ensure_roles()
	_ensure_employee_custom_fields()
	ensure_role_permissions()
	_ensure_common_activity_types()
	_ensure_desk_entry()
	_unsubmit_live_activity_sessions()


def _ensure_common_activity_types() -> None:
	"""Seed common Activity Types used on Timesheet Detail / sessions."""
	for name in ("Execution", "Development", "Meeting", "Review", "Support", "Testing"):
		if frappe.db.exists("Activity Type", name):
			continue
		try:
			frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(
				ignore_permissions=True
			)
		except Exception:
			pass


def _unsubmit_live_activity_sessions() -> None:
	"""Keep Running/Paused timers editable (never stay submitted)."""
	if not frappe.db.exists("DocType", "Tracker Activity Session"):
		return
	frappe.db.sql(
		"""
		UPDATE `tabTracker Activity Session`
		SET docstatus = 0
		WHERE docstatus = 1 AND status IN ('Running', 'Paused')
		"""
	)
	frappe.db.set_value(
		"DocType",
		"Tracker Activity Session",
		"is_submittable",
		0,
		update_modified=False,
	)


def _ensure_employee_custom_fields() -> None:
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "tracker_org_role",
					"label": "Org Role",
					"fieldtype": "Select",
					"options": "\nTop\nSub\nWorker",
					"insert_after": "reports_to",
					"description": "Top → Sub → Worker hierarchy for Task Management assignment",
				},
			]
		},
		update=True,
	)


def _ensure_activity_type(name: str) -> None:
	if not name or not frappe.db.exists("DocType", "Activity Type"):
		return
	if frappe.db.exists("Activity Type", name):
		return
	try:
		frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(
			ignore_permissions=True
		)
	except Exception:
		pass


def _ensure_desk_entry() -> None:
	"""Frappe v16 Desk uses Workspace Sidebar + Desktop Icon (not Workspace alone)."""
	# Drop retired Project Tracker leftovers that hide the real app
	for doctype in ("Desktop Icon", "Workspace Sidebar", "Module Def", "Workspace"):
		for name in frappe.get_all(
			doctype,
			filters={"name": ["in", ["Project Tracker", "project_tracker"]]},
			pluck="name",
		):
			try:
				frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
			except Exception:
				pass

	# Sync may name the sidebar "Tracker" or "Task Management"
	sidebar_name = None
	for candidate in ("Tracker", "Task Management"):
		if frappe.db.exists("Workspace Sidebar", candidate):
			sidebar_name = candidate
			break

	if frappe.db.exists("Module Def", "Tracker"):
		if sidebar_name:
			sb = frappe.get_doc("Workspace Sidebar", sidebar_name)
			changed = False
			if sb.app != "zatgo_core":
				sb.app = "zatgo_core"
				changed = True
			if sb.module != "Tracker":
				sb.module = "Tracker"
				changed = True
			if getattr(sb, "title", None) != sidebar_name:
				sb.title = sidebar_name
				changed = True
			if _sync_sidebar_items(sb):
				changed = True
			if changed:
				_save_ignore_links(sb)
		else:
			sidebar_name = "Tracker"
			sb = frappe.get_doc(
				{
					"doctype": "Workspace Sidebar",
					"name": sidebar_name,
					"title": sidebar_name,
					"header_icon": "project",
					"module": "Tracker",
					"app": "zatgo_core",
					"standard": 1,
					"items": _safe_sidebar_items(),
				}
			)
			sb.flags.ignore_links = True
			sb.insert(ignore_permissions=True)

	icons = _tracker_icons()
	# Frappe v16 Desk permits Link icons only when Desktop Icon.label.lower()
	# matches Workspace Sidebar name.lower() in bootinfo (see desktop_icon.get_desktop_icons).
	desk_label = sidebar_name or "Tracker"
	if not icons:
		if sidebar_name and frappe.db.exists("Workspace Sidebar", sidebar_name):
			icon = frappe.get_doc(
				{
					"doctype": "Desktop Icon",
					"label": desk_label,
					"app": "zatgo_core",
					"icon_type": "Link",
					"link_type": "Workspace Sidebar",
					"link_to": sidebar_name,
					"icon": "project",
					"standard": 1,
					"hidden": 0,
				}
			)
			icon.flags.ignore_links = True
			icon.insert(ignore_permissions=True)
	else:
		for name in icons:
			doc = frappe.get_doc("Desktop Icon", name)
			# autoname is field:label — change label via rename when needed
			if doc.label != desk_label or name != desk_label:
				try:
					if name != desk_label and not frappe.db.exists("Desktop Icon", desk_label):
						frappe.rename_doc(
							"Desktop Icon",
							name,
							desk_label,
							force=True,
							show_alert=False,
						)
						name = desk_label
						doc = frappe.get_doc("Desktop Icon", name)
					else:
						frappe.db.set_value("Desktop Icon", name, "label", desk_label, update_modified=False)
						doc = frappe.get_doc("Desktop Icon", name)
				except Exception:
					frappe.db.set_value("Desktop Icon", name, "label", desk_label, update_modified=False)
					doc = frappe.get_doc("Desktop Icon", name)
			changed = False
			if doc.app != "zatgo_core":
				doc.app = "zatgo_core"
				changed = True
			if doc.link_type != "Workspace Sidebar":
				doc.link_type = "Workspace Sidebar"
				changed = True
			if sidebar_name and doc.link_to != sidebar_name:
				doc.link_to = sidebar_name
				changed = True
			if doc.icon != "project":
				doc.icon = "project"
				changed = True
			if doc.hidden:
				doc.hidden = 0
				changed = True
			if doc.parent_icon:
				doc.parent_icon = ""
				changed = True
			if changed:
				_save_ignore_links(doc)

	# Workspace title/label for Desk (avoid full save — Workspace has mandatory fields)
	if frappe.db.exists("Workspace", "Tracker"):
		frappe.db.set_value("Workspace", "Tracker", "title", "Tracker", update_modified=False)
		if frappe.get_meta("Workspace").has_field("label"):
			frappe.db.set_value("Workspace", "Tracker", "label", "Tracker", update_modified=False)

	if sidebar_name and frappe.db.exists("Workspace Sidebar", sidebar_name):
		sb = frappe.get_doc("Workspace Sidebar", sidebar_name)
		changed = False
		# Keep sidebar title aligned with name so Desk label lookup stays consistent.
		if sb.title != sidebar_name:
			sb.title = sidebar_name
			changed = True
		if _sync_sidebar_items(sb):
			changed = True
		if changed:
			_save_ignore_links(sb)

	frappe.db.commit()


def _tracker_icons() -> list[str]:
	"""Desktop Icons of Tracker: linked to its sidebar, or still tagged with
	the old app name."""
	linked = frappe.get_all(
		"Desktop Icon", filters={"link_to": ["in", list(SIDEBAR_NAMES)]}, pluck="name"
	)
	legacy = frappe.get_all("Desktop Icon", filters={"app": "tracker"}, pluck="name")
	return list(dict.fromkeys(linked + legacy))
