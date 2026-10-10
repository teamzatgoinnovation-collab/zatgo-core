"""Unsubmit live activity sessions and lock DocType as non-submittable.

Timers must stay draft; a submitted session blocks Pause/Stop with
\"Cannot Update After Submit\".
"""

from __future__ import annotations

import frappe


def execute() -> None:
	frappe.db.sql(
		"""
		UPDATE `tabTracker Activity Session`
		SET docstatus = 0
		WHERE docstatus = 1 AND status IN ('Running', 'Paused')
		"""
	)
	if frappe.db.exists("DocType", "Tracker Activity Session"):
		frappe.db.set_value(
			"DocType",
			"Tracker Activity Session",
			"is_submittable",
			0,
			update_modified=False,
		)
	frappe.clear_cache(doctype="Tracker Activity Session")
