"""Unified Chat API aliases for multi-client platforms (Desk / Flutter / Electron / Web)."""

from __future__ import annotations

import json

import frappe

from zatgo_core.chat_ai.api import chat as chat_api
from zatgo_core.chat_ai.api.response import fail, ok


def _ensure_user():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.PermissionError)


@frappe.whitelist()
def chat_message(**kwargs):
	"""Alias of zatgo_core.chat_ai.api.chat.send."""
	return chat_api.send(**kwargs)


@frappe.whitelist()
def chat_session_new(**kwargs):
	return chat_api.new_session(**kwargs)


@frappe.whitelist()
def chat_session_list(**kwargs):
	return chat_api.list_sessions(**kwargs)


@frappe.whitelist()
def chat_session_rename(**kwargs):
	return chat_api.rename(**kwargs)


@frappe.whitelist()
def chat_session_archive(**kwargs):
	return chat_api.archive(**kwargs)


@frappe.whitelist()
def chat_history(**kwargs):
	return chat_api.history(**kwargs)


@frappe.whitelist()
def chat_artifacts(session=None, limit=50):
	_ensure_user()
	if not session:
		return fail("session required")
	chat_api._assert_session_access(session)
	if not frappe.db.exists("DocType", "AI Artifact"):
		return ok([])
	rows = frappe.get_all(
		"AI Artifact",
		filters={"session": session},
		fields=["name", "artifact_type", "title", "creation", "message", "plugin"],
		order_by="creation desc",
		limit_page_length=int(limit or 50),
	)
	return ok(rows)


@frappe.whitelist()
def get_artifact(name=None):
	_ensure_user()
	if not name:
		return fail("name required")
	if not frappe.db.exists("AI Artifact", name):
		return fail("not found")
	doc = frappe.get_doc("AI Artifact", name)
	chat_api._assert_session_access(doc.session)
	return ok(doc.as_dict())


@frappe.whitelist()
def chat_events_subscribe():
	"""Docs-only: clients should subscribe to realtime channel chat_ai:event."""
	return ok(
		{
			"channel": "chat_ai:event",
			"legacy": ["chat_ai:stream", "chat_ai:progress"],
			"types": [
				"thinking",
				"planning",
				"tool_started",
				"tool_progress",
				"tool_finished",
				"artifact_created",
				"assistant_message",
				"done",
				"error",
			],
		}
	)


@frappe.whitelist()
def chat_tools_list():
	_ensure_user()
	from zatgo_core.chat_ai.erpnext.orchestrator import collect_tools, load_skills
	from zatgo_core.chat_ai.erpnext.settings import get_settings_dict
	from zatgo_core.chat_ai.plugin.loader import load_all

	load_all()
	load_skills()
	settings = get_settings_dict()
	tools = collect_tools(settings=settings)
	return ok(
		[
			{
				"name": t.name,
				"description": t.description,
				"category": t.category,
				"skill": getattr(t, "skill", None),
				"source": getattr(t, "source", None),
			}
			for t in tools
		]
	)


@frappe.whitelist()
def chat_plugins_list():
	_ensure_user()
	from zatgo_core.chat_ai.plugin.registry import list_registry_rows

	return ok(list_registry_rows())


@frappe.whitelist()
def chat_connectors_list():
	_ensure_user()
	out = {"rest": [], "mcp": [], "integrations": []}
	if frappe.db.exists("DocType", "AI REST Tool"):
		out["rest"] = frappe.get_all(
			"AI REST Tool",
			fields=["name", "tool_name", "enabled", "lifecycle_status", "last_health_ok", "last_health_at"],
			limit_page_length=100,
		)
	if frappe.db.exists("DocType", "AI MCP Server"):
		out["mcp"] = frappe.get_all(
			"AI MCP Server",
			fields=["name", "label", "enabled", "lifecycle_status", "last_health_ok", "last_health_at"],
			limit_page_length=100,
		)
	if frappe.db.exists("DocType", "AI Integration Connector"):
		out["integrations"] = frappe.get_all(
			"AI Integration Connector",
			fields=["name", "label", "service", "enabled", "lifecycle_status", "last_health_ok", "last_health_at"],
			limit_page_length=100,
		)
	return ok(out)


@frappe.whitelist()
def chat_connectors_test(doctype=None, name=None):
	_ensure_user()
	frappe.only_for(("System Manager", "Chat AI Manager"))
	from zatgo_core.chat_ai.core.tool_sources.health import test_integration, test_mcp_server, test_rest_tool

	if doctype == "AI REST Tool":
		return ok(test_rest_tool(name, persist=True))
	if doctype == "AI MCP Server":
		return ok(test_mcp_server(name, persist=True))
	if doctype == "AI Integration Connector":
		return ok(test_integration(name, persist=True))
	return fail("unknown doctype")


@frappe.whitelist()
def cancel_turn(session=None):
	_ensure_user()
	if not session:
		return fail("session required")
	chat_api._assert_session_access(session)
	from zatgo_core.chat_ai.core.tool_pipeline import request_cancel

	request_cancel(session)
	return ok({"cancelled": True})


# Also expose list/get under plan names
list_artifacts = chat_artifacts
get_artifact_alias = get_artifact
