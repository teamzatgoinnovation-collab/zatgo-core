# Copyright (c) 2026, ZatGo Innovation and contributors

from __future__ import annotations

import frappe
from frappe.model.document import Document


class TrackerSettings(Document):
	pass


def get_tracker_defaults() -> dict:
	"""Return Tracker Settings defaults (safe if Single not yet saved)."""
	company = None
	activity_type = "Execution"
	try:
		if frappe.db.exists("DocType", "Tracker Settings"):
			company = frappe.db.get_single_value("Tracker Settings", "default_company")
			activity_type = (
				frappe.db.get_single_value("Tracker Settings", "default_activity_type")
				or "Execution"
			)
	except Exception:
		pass
	return {"default_company": company, "default_activity_type": activity_type}


def get_default_company() -> str | None:
	return get_tracker_defaults().get("default_company")


def get_default_activity_type() -> str:
	return get_tracker_defaults().get("default_activity_type") or "Execution"
