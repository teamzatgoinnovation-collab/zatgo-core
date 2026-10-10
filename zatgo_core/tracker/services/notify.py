"""Best-effort assign notifications via ZatGo Core hub (never blocks assign)."""

from __future__ import annotations

import frappe


def notify_assigned(*, doctype: str, name: str, users: list[str], assigner: str | None = None) -> None:
	if not users:
		return
	assigner = assigner or frappe.session.user
	subject = frappe.db.get_value(doctype, name, "subject") or name
	title = f"{doctype} assigned"
	body = f"{assigner} assigned you {doctype} {name}: {subject}"
	data = {"doctype": doctype, "name": name, "app": "tracker"}
	for user in users:
		if not user or user == assigner:
			continue
		try:
			fn = frappe.get_attr("zatgo_core.api.v1.devices.send_to_user")
			fn(user=user, title=title, body=body, data=data)
		except Exception:
			frappe.log_error(
				title="Tracker assign notify failed",
				message=frappe.get_traceback(),
			)
