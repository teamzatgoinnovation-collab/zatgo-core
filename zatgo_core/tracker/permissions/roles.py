"""Tracker role names and Role Permission Manager defaults."""

from __future__ import annotations

import frappe
from frappe.permissions import add_permission, update_permission_property

TRACKER_TOP = "Tracker Top"
TRACKER_SUB = "Tracker Sub"
TRACKER_WORKER = "Tracker Worker"

TRACKER_ROLES = (TRACKER_TOP, TRACKER_SUB, TRACKER_WORKER)

# role → (read, write, create, delete, submit, cancel)
_PERM = {
	"Project": {
		TRACKER_TOP: (1, 1, 1, 1, 0, 0),
		TRACKER_SUB: (1, 1, 1, 0, 0, 0),
		TRACKER_WORKER: (1, 0, 0, 0, 0, 0),
	},
	"Task": {
		TRACKER_TOP: (1, 1, 1, 1, 0, 0),
		TRACKER_SUB: (1, 1, 1, 0, 0, 0),
		TRACKER_WORKER: (1, 1, 0, 0, 0, 0),
	},
	"Issue": {
		TRACKER_TOP: (1, 1, 1, 1, 0, 0),
		TRACKER_SUB: (1, 1, 1, 0, 0, 0),
		TRACKER_WORKER: (1, 1, 1, 0, 0, 0),
	},
	"Timesheet": {
		TRACKER_TOP: (1, 1, 1, 1, 1, 1),
		TRACKER_SUB: (1, 1, 1, 0, 1, 0),
		TRACKER_WORKER: (1, 1, 1, 0, 0, 0),
	},
	"Tracker Activity Session": {
		TRACKER_TOP: (1, 1, 1, 1, 0, 0),
		TRACKER_SUB: (1, 1, 1, 0, 0, 0),
		TRACKER_WORKER: (1, 1, 1, 0, 0, 0),
	},
	"Employee": {
		TRACKER_TOP: (1, 1, 0, 0, 0, 0),
		TRACKER_SUB: (1, 0, 0, 0, 0, 0),
		TRACKER_WORKER: (1, 0, 0, 0, 0, 0),
	},
	"Tracker Settings": {
		TRACKER_TOP: (1, 1, 0, 0, 0, 0),
	},
}


def ensure_roles() -> None:
	for role in TRACKER_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)


def ensure_role_permissions() -> None:
	for doctype, role_map in _PERM.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role, bits in role_map.items():
			_ensure_perm(doctype, role, bits)


def _ensure_perm(doctype: str, role: str, bits: tuple[int, ...]) -> None:
	read, write, create, delete, submit, cancel = bits
	if not frappe.db.exists("DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
		add_permission(doctype, role, 0)
	for prop, val in (
		("read", read),
		("write", write),
		("create", create),
		("delete", delete),
		("submit", submit),
		("cancel", cancel),
		("report", 1 if read else 0),
		("export", 1 if read else 0),
		("print", 1 if read else 0),
	):
		update_permission_property(doctype, role, 0, prop, val)
