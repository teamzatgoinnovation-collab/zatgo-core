"""MCP client — load AI MCP Server tools (HTTP/SSE JSON-RPC style)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from zatgo_core.chat_ai.core.tool_router.spec import ToolSpec


def _user_roles() -> set[str]:
	try:
		import frappe

		return set(frappe.get_roles())
	except Exception:
		return set()


def _role_allowed(allowed_roles: str | None) -> bool:
	raw = (allowed_roles or "").strip()
	if not raw:
		return True
	wanted = {r.strip() for r in re.split(r"[,|\n]", raw) if r.strip()}
	if not wanted:
		return True
	roles = _user_roles()
	return bool(roles & wanted) or "System Manager" in roles


def _jsonrpc(url: str, method: str, params: dict | None = None, timeout: int = 60) -> Any:
	payload = {
		"jsonrpc": "2.0",
		"id": 1,
		"method": method,
		"params": params or {},
	}
	data = json.dumps(payload).encode("utf-8")
	req = urllib.request.Request(
		url,
		data=data,
		headers={"Content-Type": "application/json", "Accept": "application/json"},
		method="POST",
	)
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		raw = json.loads(resp.read().decode("utf-8"))
	if isinstance(raw, dict) and raw.get("error"):
		raise RuntimeError(str(raw["error"]))
	return raw.get("result") if isinstance(raw, dict) else raw


def discover_mcp_tools(server_doc) -> list[dict]:
	"""Call tools/list on an MCP server DocType instance; return tool descriptors."""
	transport = (getattr(server_doc, "transport", None) or "http").lower()
	url = (getattr(server_doc, "url", None) or "").strip()
	if transport == "stdio":
		# stdio requires a long-lived process; surface discovered_tools only
		return _parse_discovered(getattr(server_doc, "discovered_tools", None))
	if not url:
		return []
	# Prefer MCP tools/list over HTTP JSON-RPC
	try:
		result = _jsonrpc(url, "tools/list")
		tools = []
		if isinstance(result, dict):
			tools = result.get("tools") or []
		elif isinstance(result, list):
			tools = result
		return tools if isinstance(tools, list) else []
	except Exception:
		# Fallback: some gateways use /tools
		try:
			req = urllib.request.Request(url.rstrip("/") + "/tools", method="GET")
			with urllib.request.urlopen(req, timeout=30) as resp:
				data = json.loads(resp.read().decode("utf-8"))
			if isinstance(data, dict):
				return data.get("tools") or []
			return data if isinstance(data, list) else []
		except Exception:
			return _parse_discovered(getattr(server_doc, "discovered_tools", None))


def _parse_discovered(raw) -> list[dict]:
	if not raw:
		return []
	if isinstance(raw, list):
		return raw
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
		if isinstance(data, dict):
			return data.get("tools") or []
		if isinstance(data, list):
			return data
	except Exception:
		pass
	return []


def _make_mcp_handler(server_name: str, tool_name: str, url: str, transport: str):
	def handler(**kwargs):
		if (transport or "").lower() == "stdio":
			raise RuntimeError("MCP stdio transport is not executed in-request; use http/sse URL")
		if not url:
			raise RuntimeError(f"MCP server {server_name} has no URL")
		result = _jsonrpc(url, "tools/call", {"name": tool_name, "arguments": kwargs})
		return result

	return handler


def load_mcp_tools() -> list[ToolSpec]:
	try:
		import frappe
	except Exception:
		return []
	if not frappe.db.exists("DocType", "AI MCP Server"):
		return []
	rows = frappe.get_all(
		"AI MCP Server",
		filters={"enabled": 1},
		fields=["name", "label", "transport", "url", "allowed_roles", "discovered_tools", "lifecycle_status"],
	)
	tools: list[ToolSpec] = []
	for row in rows:
		status = (row.get("lifecycle_status") or "Draft").strip()
		# Only Enabled (or Testing for managers) load into tool router
		if status not in ("Enabled", "Testing"):
			continue
		if status == "Testing" and "System Manager" not in _user_roles() and "Chat AI Manager" not in _user_roles():
			continue
		if not _role_allowed(row.get("allowed_roles")):
			continue
		discovered = _parse_discovered(row.get("discovered_tools"))
		if not discovered and row.get("url"):
			try:
				doc = frappe.get_doc("AI MCP Server", row["name"])
				discovered = discover_mcp_tools(doc)
			except Exception:
				discovered = []
		for t in discovered:
			if not isinstance(t, dict):
				continue
			tname = t.get("name") or t.get("tool")
			if not tname:
				continue
			safe = re.sub(r"[^a-zA-Z0-9_]+", "_", tname).strip("_")
			fq = f"mcp_{row['name'][:8]}_{safe}"[:140]
			params = t.get("inputSchema") or t.get("parameters") or {
				"type": "object",
				"properties": {},
				"additionalProperties": True,
			}
			tools.append(
				ToolSpec(
					name=fq,
					description=t.get("description") or f"MCP tool {tname} via {row.get('label')}",
					parameters=params if isinstance(params, dict) else {
						"type": "object",
						"properties": {},
						"additionalProperties": True,
					},
					handler=_make_mcp_handler(
						row["name"], tname, row.get("url") or "", row.get("transport") or "http"
					),
					source="mcp",
					category="read",
					skill="integrations",
					mcp_server=row["name"],
					mcp_tool=tname,
				)
			)
	return tools


def refresh_discovered_tools(server_name: str) -> list[dict]:
	"""Discover and persist tools on an AI MCP Server document."""
	import frappe

	doc = frappe.get_doc("AI MCP Server", server_name)
	tools = discover_mcp_tools(doc)
	doc.discovered_tools = frappe.as_json(tools)
	doc.save(ignore_permissions=True)
	return tools
