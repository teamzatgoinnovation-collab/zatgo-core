"""Approval Engine — Workflow → Role → Permission → DocStatus → Workflow Action."""

from __future__ import annotations

import frappe
from frappe.model.workflow import apply_workflow, get_transitions

from zatgo_core.chat_ai.erpnext.permissions import can_submit, can_write, require


def list_actions(doctype: str, name: str) -> dict:
	require(doctype, "read", name)
	doc = frappe.get_doc(doctype, name)
	transitions = []
	try:
		for t in get_transitions(doc) or []:
			transitions.append(
				{
					"action": t.get("action"),
					"next_state": t.get("next_state"),
					"state": t.get("state"),
					"allowed": t.get("allowed"),
				}
			)
	except Exception:
		transitions = []
	return {
		"doctype": doctype,
		"name": name,
		"docstatus": doc.docstatus,
		"workflow_state": getattr(doc, "workflow_state", None),
		"actions": transitions,
		"can_submit": bool(getattr(doc, "docstatus", None) == 0 and can_submit(doctype, name)),
		"can_cancel": bool(getattr(doc, "docstatus", None) == 1 and can_write(doctype, name)),
	}


def apply_action(doctype: str, name: str, action: str, comment: str | None = None) -> dict:
	"""Apply workflow action or submit/cancel fallbacks."""
	require(doctype, "write", name)
	doc = frappe.get_doc(doctype, name)
	action_l = (action or "").strip()

	# Explicit submit/cancel without workflow
	if action_l.lower() == "submit":
		if doc.docstatus != 0:
			return {"ok": False, "stage": "docstatus", "reason": "Document is not in draft"}
		require(doctype, "submit", name)
		doc.submit()
		return {"ok": True, "doctype": doctype, "name": name, "docstatus": doc.docstatus}

	if action_l.lower() == "cancel":
		if doc.docstatus != 1:
			return {"ok": False, "stage": "docstatus", "reason": "Document is not submitted"}
		doc.cancel()
		return {"ok": True, "doctype": doctype, "name": name, "docstatus": doc.docstatus}

	# Workflow path
	try:
		transitions = get_transitions(doc) or []
	except Exception as exc:
		return {"ok": False, "stage": "workflow", "reason": str(exc)}

	match = None
	for t in transitions:
		if (t.get("action") or "").lower() == action_l.lower():
			match = t
			break
	if not match and action_l.lower() in ("approve", "reject"):
		# Prefer action containing approve/reject
		for t in transitions:
			if action_l.lower() in (t.get("action") or "").lower():
				match = t
				break

	if not match:
		return {
			"ok": False,
			"stage": "workflow",
			"reason": f"Action '{action}' not available",
			"available": [t.get("action") for t in transitions],
		}

	allowed_role = match.get("allowed")
	if allowed_role and allowed_role not in frappe.get_roles():
		return {"ok": False, "stage": "role", "reason": f"Requires role {allowed_role}"}

	try:
		apply_workflow(doc, match.get("action"))
		if comment:
			doc.add_comment("Comment", comment)
		doc.reload()
		return {
			"ok": True,
			"doctype": doctype,
			"name": name,
			"action": match.get("action"),
			"workflow_state": getattr(doc, "workflow_state", None),
			"docstatus": doc.docstatus,
		}
	except frappe.PermissionError as exc:
		return {"ok": False, "stage": "permission", "reason": str(exc)}
	except Exception as exc:
		return {"ok": False, "stage": "action", "reason": str(exc)}
