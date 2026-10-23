"""Integration connectors — GitHub, Slack, Custom HTTP (others stub)."""

from __future__ import annotations

import json
import re
from typing import Any

from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec
from zatgo_core.chat_ai.core.tool_sources import net

_STUB_SERVICES = {"WhatsApp", "Google Drive", "Jira", "GitLab", "Notion"}


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


def _token(docname: str) -> str:
	import frappe

	try:
		return frappe.get_doc("AI Integration Connector", docname).get_password("api_token") or ""
	except Exception:
		return ""


def _http_json(url: str, *, method: str = "GET", headers: dict | None = None, body: dict | None = None):
	data = json.dumps(body).encode("utf-8") if body is not None else None
	hdrs = {"Accept": "application/json", "Content-Type": "application/json"}
	if headers:
		hdrs.update(headers)
	resp = net.request(url, method=method, headers=hdrs, body=data)
	raw = resp.text()
	if resp.status >= 400:
		raise RuntimeError(f"HTTP {resp.status}: {raw[:2000]}")
	try:
		return json.loads(raw)
	except json.JSONDecodeError:
		return {"raw": raw[:8000]}


def _github_tools(row: dict) -> list[ToolSpec]:
	docname = row["name"]
	label = row.get("label") or "GitHub"
	base = (row.get("base_url") or "https://api.github.com").rstrip("/")
	prefix = f"github_{docname[:8]}"

	def list_issues(owner: str, repo: str, state: str = "open", **_):
		token = _token(docname)
		return _http_json(
			f"{base}/repos/{owner}/{repo}/issues?state={state}",
			headers={"Authorization": f"Bearer {token}", "User-Agent": "chat-ai"},
		)

	def create_issue(owner: str, repo: str, title: str, body: str = "", **_):
		token = _token(docname)
		return _http_json(
			f"{base}/repos/{owner}/{repo}/issues",
			method="POST",
			headers={"Authorization": f"Bearer {token}", "User-Agent": "chat-ai"},
			body={"title": title, "body": body},
		)

	return [
		ToolSpec(
			name=f"{prefix}_list_issues",
			description=f"List GitHub issues ({label})",
			parameters={
				"type": "object",
				"properties": {
					"owner": {"type": "string"},
					"repo": {"type": "string"},
					"state": {"type": "string"},
				},
				"required": ["owner", "repo"],
			},
			handler=list_issues,
			source="plugin",
			category=CATEGORY_READ,
			skill="integrations",
			endpoint_ref=docname,
		),
		ToolSpec(
			name=f"{prefix}_create_issue",
			description=f"Create a GitHub issue ({label})",
			parameters={
				"type": "object",
				"properties": {
					"owner": {"type": "string"},
					"repo": {"type": "string"},
					"title": {"type": "string"},
					"body": {"type": "string"},
				},
				"required": ["owner", "repo", "title"],
			},
			handler=create_issue,
			source="plugin",
			category=CATEGORY_WRITE,
			skill="integrations",
			confirmation_required=True,
			endpoint_ref=docname,
		),
	]


def _slack_tools(row: dict) -> list[ToolSpec]:
	docname = row["name"]
	label = row.get("label") or "Slack"
	base = (row.get("base_url") or "https://slack.com/api").rstrip("/")
	prefix = f"slack_{docname[:8]}"

	def post_message(channel: str, text: str, **_):
		token = _token(docname)
		return _http_json(
			f"{base}/chat.postMessage",
			method="POST",
			headers={"Authorization": f"Bearer {token}"},
			body={"channel": channel, "text": text},
		)

	return [
		ToolSpec(
			name=f"{prefix}_post_message",
			description=f"Post a Slack message ({label})",
			parameters={
				"type": "object",
				"properties": {
					"channel": {"type": "string"},
					"text": {"type": "string"},
				},
				"required": ["channel", "text"],
			},
			handler=post_message,
			source="plugin",
			category=CATEGORY_WRITE,
			skill="integrations",
			confirmation_required=True,
			endpoint_ref=docname,
		),
	]


READ_METHODS = ("GET", "HEAD")
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _custom_tools(row: dict) -> list[ToolSpec]:
	"""Custom HTTP connector: one read-only tool (GET/HEAD) and one write tool (POST/PUT/PATCH/DELETE) that
	the user has to confirm -- a model can no longer change data on the other side through the "read" tool."""
	docname = row["name"]
	label = row.get("label") or "Custom"
	base = (row.get("base_url") or "").rstrip("/")
	prefix = f"custom_{docname[:8]}"
	if not base:
		return []

	def call(path: str, method: str, body: dict | None, allowed: tuple[str, ...]):
		method = (method or allowed[0]).upper()
		if method not in allowed:
			raise ValueError(f"This tool only does {', '.join(allowed)}; use the other tool of the connector for {method}.")
		token = _token(docname)
		auth_type = (row.get("auth_type") or "Bearer").strip()
		headers = {}
		if token:
			if auth_type == "API Key":
				headers["X-API-Key"] = token
			elif auth_type == "Basic":
				headers["Authorization"] = f"Basic {token}"
			else:
				headers["Authorization"] = f"Bearer {token}"
		url = base + (path if path.startswith("/") else "/" + path)
		return _http_json(url, method=method, headers=headers, body=body)

	def read_request(path: str = "/", method: str = "GET", **_):
		return call(path, method, None, READ_METHODS)

	def write_request(path: str = "/", method: str = "POST", body: dict | None = None, **_):
		return call(path, method, body, WRITE_METHODS)

	return [
		ToolSpec(
			name=f"{prefix}_request",
			description=f"Read-only HTTP request (GET/HEAD) via connector {label}",
			parameters={
				"type": "object",
				"properties": {"path": {"type": "string"}, "method": {"type": "string", "enum": list(READ_METHODS)}},
			},
			handler=read_request,
			source="plugin",
			category=CATEGORY_READ,
			skill="integrations",
			endpoint_ref=docname,
		),
		ToolSpec(
			name=f"{prefix}_write_request",
			description=f"HTTP request that changes data (POST/PUT/PATCH/DELETE) via connector {label}; the user confirms it first",
			parameters={
				"type": "object",
				"properties": {
					"path": {"type": "string"},
					"method": {"type": "string", "enum": list(WRITE_METHODS)},
					"body": {"type": "object"},
				},
			},
			handler=write_request,
			source="plugin",
			category=CATEGORY_WRITE,
			skill="integrations",
			confirmation_required=True,
			endpoint_ref=docname,
		),
	]


def _stub_tools(row: dict) -> list[ToolSpec]:
	service = row.get("service") or "Unknown"
	docname = row["name"]
	prefix = f"stub_{docname[:8]}"

	def not_configured(**_):
		return {
			"ok": False,
			"error": f"{service} connector is configured but not implemented yet. Use Custom HTTP or wait for a later release.",
		}

	return [
		ToolSpec(
			name=f"{prefix}_status",
			description=f"{service} integration status (not fully implemented)",
			parameters={"type": "object", "properties": {}},
			handler=not_configured,
			source="plugin",
			category=CATEGORY_READ,
			skill="integrations",
			endpoint_ref=docname,
		),
	]


def load_integration_tools() -> list[ToolSpec]:
	try:
		import frappe
	except Exception:
		return []
	if not frappe.db.exists("DocType", "AI Integration Connector"):
		return []
	rows = frappe.get_all(
		"AI Integration Connector",
		filters={"enabled": 1},
		fields=[
			"name",
			"service",
			"label",
			"auth_type",
			"base_url",
			"allowed_roles",
			"workspace_id",
			"lifecycle_status",
		],
	)
	tools: list[ToolSpec] = []
	for row in rows:
		status = (row.get("lifecycle_status") or "Draft").strip()
		if status not in ("Enabled", "Testing"):
			continue
		if status == "Testing" and "System Manager" not in _user_roles() and "Chat AI Manager" not in _user_roles():
			continue
		if not _role_allowed(row.get("allowed_roles")):
			continue
		service = row.get("service") or "Custom"
		if service == "GitHub":
			tools.extend(_github_tools(row))
		elif service == "Slack":
			tools.extend(_slack_tools(row))
		elif service == "Custom":
			tools.extend(_custom_tools(row))
		elif service in _STUB_SERVICES:
			tools.extend(_stub_tools(row))
		else:
			tools.extend(_stub_tools(row))
	return tools
