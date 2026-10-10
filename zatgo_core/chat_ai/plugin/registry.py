"""Enabled plugins gate + registry persistence helpers."""

from __future__ import annotations

import json
from typing import Any


_DISCOVERED: dict[str, dict] = {}
_STATUS_SECTION_PROVIDERS: list = []


def set_discovered(entries: list[dict]):
	_DISCOVERED.clear()
	for e in entries or []:
		key = e.get("plugin_name") or e.get("name") or ""
		if key:
			_DISCOVERED[key] = e


def get_discovered() -> list[dict]:
	return list(_DISCOVERED.values())


def is_plugin_enabled(plugin_name: str, settings: dict | None = None) -> bool:
	settings = settings or {}
	if not settings.get("enable_plugin_discovery", 1):
		# discovery off still allows hook-based plugins; folder plugins skipped by loader
		return True
	raw = (settings.get("enabled_plugins") or "").strip()
	if not raw:
		return True  # empty = all discovered
	allowed = {x.strip() for x in raw.replace(",", "\n").splitlines() if x.strip()}
	return plugin_name in allowed


def register_status_section(provider):
	"""Plugins register callables: provider(company, context) -> dict|None."""
	if callable(provider):
		_STATUS_SECTION_PROVIDERS.append(provider)
	return provider


def get_status_section_providers() -> list:
	return list(_STATUS_SECTION_PROVIDERS)


def clear_status_section_providers():
	_STATUS_SECTION_PROVIDERS.clear()


def persist_registry(entries: list[dict]):
	"""Upsert AI Plugin Registry rows when DocType exists."""
	try:
		import frappe
	except Exception:
		return
	if not frappe.db.exists("DocType", "AI Plugin Registry"):
		return
	seen = set()
	for e in entries or []:
		app = e.get("app") or ""
		pname = e.get("plugin_name") or e.get("name") or ""
		if not app or not pname:
			continue
		seen.add((app, pname))
		existing = frappe.db.get_value(
			"AI Plugin Registry",
			{"app": app, "plugin_name": pname},
			"name",
		)
		payload = {
			"app": app,
			"plugin_name": pname,
			"version": e.get("version") or "",
			"enabled": 1 if e.get("enabled", True) else 0,
			"manifest_json": json.dumps(e.get("manifest") or e, default=str),
			"discovered_at": frappe.utils.now_datetime(),
		}
		if existing:
			doc = frappe.get_doc("AI Plugin Registry", existing)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "AI Plugin Registry", **payload}).insert(ignore_permissions=True)


def list_registry_rows() -> list[dict]:
	try:
		import frappe
	except Exception:
		return get_discovered()
	if not frappe.db.exists("DocType", "AI Plugin Registry"):
		return get_discovered()
	return frappe.get_all(
		"AI Plugin Registry",
		fields=["name", "app", "plugin_name", "version", "enabled", "discovered_at"],
		order_by="app asc",
	)
