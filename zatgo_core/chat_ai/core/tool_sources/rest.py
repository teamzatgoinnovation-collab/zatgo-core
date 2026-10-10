"""Load AI REST Tool DocTypes into ToolSpec handlers."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
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


def _parse_schema(raw: str | None) -> dict:
	if not raw:
		return {"type": "object", "properties": {}, "additionalProperties": True}
	try:
		data = json.loads(raw)
		if isinstance(data, dict):
			return data
	except Exception:
		pass
	return {"type": "object", "properties": {}, "additionalProperties": True}


def _auth_headers(auth_type: str, token: str) -> dict[str, str]:
	headers = {"Content-Type": "application/json", "Accept": "application/json"}
	auth_type = (auth_type or "None").strip()
	token = token or ""
	if not token or auth_type == "None":
		return headers
	if auth_type == "Bearer":
		headers["Authorization"] = f"Bearer {token}"
	elif auth_type == "API Key":
		headers["X-API-Key"] = token
	elif auth_type == "Basic":
		# token may be "user:pass" or already base64
		if ":" in token:
			encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
		else:
			encoded = token
		headers["Authorization"] = f"Basic {encoded}"
	return headers


def _format_url(template: str, args: dict) -> str:
	url = template or ""
	# {param} substitution from args
	def repl(m):
		key = m.group(1)
		val = args.get(key, "")
		return urllib.parse.quote(str(val), safe="")

	url = re.sub(r"\{(\w+)\}", repl, url)
	return url


def _make_handler(row: dict):
	method = (row.get("method") or "GET").upper()
	url_template = row.get("url_template") or ""
	auth_type = row.get("auth_type") or "None"
	# Password field: may need get_password at call time
	docname = row.get("name")

	def handler(**kwargs):
		import frappe

		token = ""
		if docname:
			try:
				token = frappe.get_doc("AI REST Tool", docname).get_password("auth_token") or ""
			except Exception:
				token = ""
		url = _format_url(url_template, kwargs)
		headers = _auth_headers(auth_type, token)
		body = None
		if method in ("POST", "PUT", "PATCH"):
			payload = kwargs.get("body")
			if payload is None:
				payload = {k: v for k, v in kwargs.items() if k not in ("body",)}
			body = json.dumps(payload).encode("utf-8")
		elif method == "GET" and kwargs:
			# leftover query params not in path
			parsed = urllib.parse.urlparse(url)
			q = dict(urllib.parse.parse_qsl(parsed.query))
			for k, v in kwargs.items():
				if f"{{{k}}}" not in url_template:
					q[k] = str(v)
			url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q)))
		req = urllib.request.Request(url, data=body, headers=headers, method=method)
		try:
			with urllib.request.urlopen(req, timeout=60) as resp:
				raw = resp.read().decode("utf-8", errors="replace")
				try:
					return {"status": resp.status, "data": json.loads(raw)}
				except json.JSONDecodeError:
					return {"status": resp.status, "data": raw[:8000]}
		except urllib.error.HTTPError as exc:
			err_body = exc.read().decode("utf-8", errors="replace")[:2000]
			raise RuntimeError(f"REST {exc.code}: {err_body}") from exc

	return handler


def load_rest_tools() -> list[ToolSpec]:
	try:
		import frappe
	except Exception:
		return []
	if not frappe.db.exists("DocType", "AI REST Tool"):
		return []
	rows = frappe.get_all(
		"AI REST Tool",
		filters={"enabled": 1},
		fields=[
			"name",
			"tool_name",
			"description",
			"method",
			"url_template",
			"auth_type",
			"json_schema",
			"allowed_roles",
			"category",
			"lifecycle_status",
		],
	)
	tools: list[ToolSpec] = []
	for row in rows:
		status = (row.get("lifecycle_status") or "Enabled").strip()
		if status and status not in ("Enabled", "Testing"):
			continue
		if status == "Testing" and "System Manager" not in _user_roles() and "Chat AI Manager" not in _user_roles():
			continue
		if not _role_allowed(row.get("allowed_roles")):
			continue
		name = row.get("tool_name") or row.get("name")
		tools.append(
			ToolSpec(
				name=name,
				description=row.get("description") or f"REST tool {name}",
				parameters=_parse_schema(row.get("json_schema")),
				handler=_make_handler(row),
				source="rest",
				category=(row.get("category") or "read").lower(),
				skill="integrations",
				endpoint_ref=row.get("name") or "",
			)
		)
	return tools


def build_rest_tool_spec(
	*,
	tool_name: str,
	description: str = "",
	method: str = "GET",
	url_template: str = "https://example.com/{id}",
	json_schema: dict | None = None,
	category: str = "read",
	handler=None,
) -> ToolSpec:
	"""Pure helper for tests — build a ToolSpec shaped like a REST tool."""
	return ToolSpec(
		name=tool_name,
		description=description or tool_name,
		parameters=json_schema
		or {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
		handler=handler or (lambda **kw: {"ok": True, "args": kw}),
		source="rest",
		category=category,
		skill="integrations",
		endpoint_ref="test",
	)
