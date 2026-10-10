"""Workflow-related notifications (gated)."""

from __future__ import annotations

import frappe


def on_workflow_action(doc, method=None):
	try:
		if not frappe.db.get_single_value("Chat AI Settings", "enable_workflow_events"):
			return
		from zatgo_core.chat_ai.erpnext.events.realtime_events import publish_notify

		state = getattr(doc, "workflow_state", "")
		publish_notify(doc.doctype, f"{doc.name} workflow → {state}")
	except Exception:
		pass
