"""Admin metrics API — Chat AI Manager / System Manager only."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from zatgo_core.chat_ai.api.response import fail, ok
from zatgo_core.chat_ai.core.providers.registry import from_settings
from zatgo_core.chat_ai.erpnext.settings import get_settings_dict


def _require_manager():
	roles = set(frappe.get_roles())
	if "System Manager" not in roles and "Chat AI Manager" not in roles:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_dashboard_summary():
	_require_manager()
	sessions = frappe.db.count("AI Chat Session")
	messages = frappe.db.count("AI Chat Message")
	tool_logs = frappe.db.count("AI Tool Log")
	errors = frappe.db.count("AI Tool Log", {"success": 0})
	usage = frappe.get_all(
		"AI Usage Daily",
		fields=["sum(tokens_in) as tin", "sum(tokens_out) as tout", "sum(cost_estimate) as cost", "avg(avg_latency_ms) as latency"],
		limit=1,
	)
	u = usage[0] if usage else {}
	health = frappe.get_all(
		"AI Provider Health Log",
		fields=["provider", "ok", "latency_ms", "error", "checked_at"],
		order_by="checked_at desc",
		limit_page_length=5,
	)
	return ok(
		{
			"sessions": sessions,
			"messages": messages,
			"tool_logs": tool_logs,
			"errors": errors,
			"tokens_in": u.get("tin") or 0,
			"tokens_out": u.get("tout") or 0,
			"cost_estimate": u.get("cost") or 0,
			"avg_latency_ms": u.get("latency") or 0,
			"provider_health": health,
		}
	)


@frappe.whitelist()
def list_errors(limit=50):
	_require_manager()
	rows = frappe.get_all(
		"AI Tool Log",
		filters={"success": 0},
		fields=["name", "tool_name", "user", "error", "creation", "latency_ms"],
		order_by="creation desc",
		limit_page_length=int(limit or 50),
	)
	return ok(rows)


@frappe.whitelist()
def ping_provider():
	_require_manager()
	settings = get_settings_dict()
	provider = from_settings(settings)
	ok_flag, latency, err = provider.ping()
	doc = frappe.get_doc(
		{
			"doctype": "AI Provider Health Log",
			"provider": settings.get("provider") or provider.name,
			"ok": 1 if ok_flag else 0,
			"latency_ms": latency,
			"error": err,
			"capabilities_json": frappe.as_json(provider.capabilities.as_dict()),
			"checked_at": now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	return ok({"ok": ok_flag, "latency_ms": latency, "error": err, "capabilities": provider.capabilities.as_dict()})
