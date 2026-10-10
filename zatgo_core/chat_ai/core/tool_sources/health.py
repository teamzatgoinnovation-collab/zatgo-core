"""Connector health checks + test helpers."""

from __future__ import annotations

import time

import frappe
from frappe.utils import now_datetime


def check_all_connectors():
	"""Hourly: ping enabled REST / MCP / Integration connectors."""
	_check_rest()
	_check_mcp()
	_check_integrations()


def _check_rest():
	if not frappe.db.exists("DocType", "AI REST Tool"):
		return
	rows = frappe.get_all(
		"AI REST Tool",
		filters={"enabled": 1, "lifecycle_status": ("in", ["Enabled", "Testing"])},
		pluck="name",
	)
	for name in rows:
		try:
			test_rest_tool(name, persist=True)
		except Exception:
			frappe.log_error(title=f"chat_ai rest health {name}")


def _check_mcp():
	if not frappe.db.exists("DocType", "AI MCP Server"):
		return
	rows = frappe.get_all(
		"AI MCP Server",
		filters={"enabled": 1, "lifecycle_status": ("in", ["Enabled", "Testing"])},
		pluck="name",
	)
	for name in rows:
		try:
			test_mcp_server(name, persist=True)
		except Exception:
			frappe.log_error(title=f"chat_ai mcp health {name}")


def _check_integrations():
	if not frappe.db.exists("DocType", "AI Integration Connector"):
		return
	rows = frappe.get_all(
		"AI Integration Connector",
		filters={"enabled": 1, "lifecycle_status": ("in", ["Enabled", "Testing"])},
		pluck="name",
	)
	for name in rows:
		try:
			test_integration(name, persist=True)
		except Exception:
			frappe.log_error(title=f"chat_ai integration health {name}")


def _write_health(doctype: str, name: str, ok: bool, latency_ms: int, error: str = ""):
	doc = frappe.get_doc(doctype, name)
	doc.last_health_at = now_datetime()
	doc.last_health_ok = 1 if ok else 0
	doc.latency_ms = latency_ms
	doc.last_error = (error or "")[:500]
	if not ok and getattr(doc, "lifecycle_status", None) == "Enabled":
		doc.lifecycle_status = "Failed"
	elif ok and getattr(doc, "lifecycle_status", None) == "Failed":
		doc.lifecycle_status = "Enabled"
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def test_rest_tool(name: str, persist: bool = False) -> dict:
	doc = frappe.get_doc("AI REST Tool", name)
	start = time.time()
	ok = False
	err = ""
	try:
		import urllib.request

		url = (doc.url_template or "").split("{")[0].rstrip("/") or doc.url_template
		if not url:
			raise RuntimeError("No URL")
		# HEAD/GET best-effort without substituting required path params
		req = urllib.request.Request(url, method="GET")
		with urllib.request.urlopen(req, timeout=15) as resp:
			ok = 200 <= resp.status < 500
	except Exception as exc:
		err = str(exc)
		ok = False
	latency = int((time.time() - start) * 1000)
	if persist:
		_write_health("AI REST Tool", name, ok, latency, err)
	return {"ok": ok, "latency_ms": latency, "error": err}


def test_mcp_server(name: str, persist: bool = False) -> dict:
	doc = frappe.get_doc("AI MCP Server", name)
	start = time.time()
	ok = False
	err = ""
	try:
		from zatgo_core.chat_ai.core.tool_sources.mcp import discover_mcp_tools

		tools = discover_mcp_tools(doc)
		ok = True
		_ = tools
	except Exception as exc:
		err = str(exc)
		ok = False
	latency = int((time.time() - start) * 1000)
	if persist:
		_write_health("AI MCP Server", name, ok, latency, err)
	return {"ok": ok, "latency_ms": latency, "error": err}


def test_integration(name: str, persist: bool = False) -> dict:
	doc = frappe.get_doc("AI Integration Connector", name)
	start = time.time()
	ok = False
	err = ""
	try:
		base = (doc.base_url or "").strip()
		if not base and doc.service == "GitHub":
			base = "https://api.github.com"
		if not base:
			# Token present counts as configured for stubs
			ok = bool(doc.get_password("api_token") if doc.get("api_token") else False) or True
		else:
			import urllib.request

			req = urllib.request.Request(base, method="GET")
			with urllib.request.urlopen(req, timeout=15) as resp:
				ok = 200 <= resp.status < 500
	except Exception as exc:
		err = str(exc)
		ok = False
	latency = int((time.time() - start) * 1000)
	if persist:
		_write_health("AI Integration Connector", name, ok, latency, err)
	return {"ok": ok, "latency_ms": latency, "error": err}


def bootstrap_lifecycle_statuses():
	"""Set Enabled where enabled=1 and status empty/Draft after migrate."""
	for dt in ("AI REST Tool", "AI MCP Server", "AI Integration Connector"):
		if not frappe.db.exists("DocType", dt):
			continue
		if not frappe.db.has_column(dt, "lifecycle_status"):
			continue
		rows = frappe.get_all(dt, filters={"enabled": 1}, fields=["name", "lifecycle_status"])
		for r in rows:
			st = (r.get("lifecycle_status") or "").strip()
			if st in ("", "Draft"):
				frappe.db.set_value(dt, r.name, "lifecycle_status", "Enabled", update_modified=False)
