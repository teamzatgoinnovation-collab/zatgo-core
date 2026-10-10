"""Build Context Stack from client_context + Frappe session."""

from __future__ import annotations

import frappe

from zatgo_core.chat_ai.erpnext.context.defaults import resolve_intelligent_defaults


def build_context_stack(client_context: dict | None = None, entities: dict | None = None) -> dict:
	client_context = client_context or {}
	stack = {
		"conversation": {},
		"entity_memory": entities or {},
		"route_context": client_context.get("route") or {},
		"recent_documents": client_context.get("recent") or _recent_documents(),
		"current_form": client_context.get("form") or {},
		"current_company": _current_company(),
		"current_user": _current_user(),
		"workspace_context": client_context.get("workspace") or {},
	}
	# Intelligent defaults (company, warehouse, etc.)
	resolved = resolve_intelligent_defaults(stack)
	if resolved.get("values"):
		stack["intelligent_defaults"] = resolved["values"]
	if resolved.get("assumptions"):
		stack["assumptions"] = resolved["assumptions"]
	# Drop empty layers
	return {k: v for k, v in stack.items() if v}


def _current_user() -> dict:
	user = frappe.session.user
	roles = frappe.get_roles(user)
	info = {"user": user, "roles": roles}
	if frappe.db.exists("DocType", "Employee") and frappe.db.exists("Employee", {"user_id": user}):
		info["employee"] = frappe.db.get_value("Employee", {"user_id": user}, "name")
	return info


def _current_company() -> dict:
	company = frappe.defaults.get_user_default("Company")
	if not company:
		return {}
	return {"company": company}


def _recent_documents() -> list:
	try:
		from frappe.utils.user import User

		# boot recent may not be available server-side; return empty
		return []
	except Exception:
		return []
