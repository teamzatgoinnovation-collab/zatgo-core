"""Integration connectors — GitHub, Slack, Custom HTTP (others stub)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ, CATEGORY_WRITE, ToolSpec

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
	req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
	try:
		with urllib.request.urlopen(req, timeout=60) as resp:
			raw = resp.read().decode("utf-8", errors="replace")
			try:
				return json.loads(raw)
			except json.JSONDecodeError:
				return {"raw": raw[:8000]}
	except urllib.error.HTTPError as exc:
		err = exc.read().decode("utf-8", errors="replace")[:2000]
		raise RuntimeError(f"HTTP {exc.code}: {err}") from exc


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


def _custom_tools(row: dict) -> list[ToolSpec]:
	docname = row["name"]
	label = row.get("label") or "Custom"
	base = (row.get("base_url") or "").rstrip("/")
	prefix = f"custom_{docname[:8]}"
	if not base:
		return []

	def request(path: str = "/", method: str = "GET", body: dict | None = None, **_):
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
		return _http_json(url, method=method.upper(), headers=headers, body=body)

	return [
		ToolSpec(
			name=f"{prefix}_request",
			description=f"HTTP request via connector {label}",
			parameters={
				"type": "object",
				"properties": {
					"path": {"type": "string"},
					"method": {"type": "string"},
					"body": {"type": "object"},
				},
			},
			handler=request,
			source="plugin",
			category=CATEGORY_READ,
			skill="integrations",
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
