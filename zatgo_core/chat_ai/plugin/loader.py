"""Load chat_ai_plugins hooks, built-in commands, and chat_ai_plugin/ auto-discovery."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import frappe

from zatgo_core.chat_ai.plugin.api import register_commands, register_skill_path, register_tools
from zatgo_core.chat_ai.plugin.manifest import parse_manifest_module
from zatgo_core.chat_ai.plugin.registry import (
	clear_status_section_providers,
	is_plugin_enabled,
	persist_registry,
	register_status_section,
	set_discovered,
)


def load_all(settings: dict | None = None):
	"""Load hooks + folder plugins. Safe to call every turn."""
	settings = settings or _safe_settings()
	_register_builtin_commands()
	clear_status_section_providers()

	# 1) Explicit hooks
	hooks = frappe.get_hooks("chat_ai_plugins") or []
	for path in hooks:
		try:
			fn = frappe.get_attr(path)
			fn()
		except Exception:
			frappe.log_error(title=f"chat_ai plugin {path}")

	# Legacy hooks
	for key in ("chat_ai_skills", "chat_ai_tools", "chat_ai_providers"):
		for path in frappe.get_hooks(key) or []:
			try:
				fn = frappe.get_attr(path)
				if callable(fn):
					fn()
			except Exception:
				frappe.log_error(title=f"chat_ai legacy hook {path}")

	# 2) Auto-discover chat_ai_plugin packages
	if settings.get("enable_plugin_discovery", 1):
		discovered = discover_installed_apps(settings=settings)
		set_discovered(discovered)
		try:
			persist_registry(discovered)
		except Exception:
			frappe.log_error(title="chat_ai plugin registry persist")


def discover_installed_apps(settings: dict | None = None) -> list[dict]:
	settings = settings or _safe_settings()
	entries: list[dict] = []
	for app in frappe.get_installed_apps():
		try:
			entry = _load_app_plugin(app, settings=settings)
			if entry:
				entries.append(entry)
		except Exception:
			frappe.log_error(title=f"chat_ai discover {app}")
	return entries


def _load_app_plugin(app: str, settings: dict | None = None) -> dict | None:
	"""Import <app>.chat_ai_plugin if present and register contents."""
	mod_name = f"{app}.chat_ai_plugin"
	try:
		pkg = importlib.import_module(mod_name)
	except ImportError:
		# Also accept package path without import (skills-only folder)
		pkg_path = _plugin_path(app)
		if not pkg_path:
			return None
		try:
			pkg = importlib.import_module(mod_name)
		except Exception:
			return None
	except Exception:
		return None

	# Manifest
	try:
		manifest_mod = importlib.import_module(f"{mod_name}.manifest")
		manifest = parse_manifest_module(manifest_mod, app=app)
	except ImportError:
		from zatgo_core.chat_ai.plugin.manifest import validate_manifest

		manifest = validate_manifest({"name": f"{app}_plugin"}, app=app)
	except Exception as exc:
		frappe.log_error(title=f"chat_ai manifest {app}", message=str(exc))
		return None

	if not is_plugin_enabled(manifest.name, settings):
		return {
			"app": app,
			"plugin_name": manifest.name,
			"version": manifest.version,
			"enabled": False,
			"manifest": manifest.to_dict(),
		}

	# Skills path
	skills_dir = _plugin_subdir(app, "skills")
	if skills_dir:
		register_skill_path(str(skills_dir))

	# tools.py
	try:
		tools_mod = importlib.import_module(f"{mod_name}.tools")
		if hasattr(tools_mod, "get_tools"):
			register_tools(tools_mod.get_tools())
	except ImportError:
		pass
	except Exception:
		frappe.log_error(title=f"chat_ai plugin tools {app}")

	# prompts — register fragments
	try:
		from zatgo_core.chat_ai.core.prompts.framework import PromptBundleRegistry

		prompts_dir = _plugin_subdir(app, "prompts")
		if prompts_dir:
			PromptBundleRegistry.register_plugin_dir(manifest.name, str(prompts_dir))
	except Exception:
		pass

	# permissions.py
	try:
		perm_mod = importlib.import_module(f"{mod_name}.permissions")
		if hasattr(perm_mod, "register_rules"):
			from zatgo_core.chat_ai.erpnext.permissions.engine import PermissionEngine

			perm_mod.register_rules(PermissionEngine)
	except ImportError:
		pass
	except Exception:
		frappe.log_error(title=f"chat_ai plugin perms {app}")

	# knowledge.py
	try:
		know_mod = importlib.import_module(f"{mod_name}.knowledge")
		if hasattr(know_mod, "get_providers"):
			from zatgo_core.chat_ai.core.knowledge.base import register_provider

			for p in know_mod.get_providers() or []:
				register_provider(p)
	except ImportError:
		pass
	except Exception:
		frappe.log_error(title=f"chat_ai plugin knowledge {app}")

	# events.py (optional handlers stored via register_events)
	try:
		events_mod = importlib.import_module(f"{mod_name}.events")
		if hasattr(events_mod, "get_handlers"):
			from zatgo_core.chat_ai.plugin.api import register_events

			register_events(events_mod.get_handlers() or {})
	except ImportError:
		pass
	except Exception:
		frappe.log_error(title=f"chat_ai plugin events {app}")

	# status sections
	try:
		status_mod = importlib.import_module(f"{mod_name}.status")
		if hasattr(status_mod, "get_sections"):
			for fn in status_mod.get_sections() or []:
				register_status_section(fn)
		elif hasattr(status_mod, "status_section"):
			register_status_section(status_mod.status_section)
	except ImportError:
		pass
	except Exception:
		frappe.log_error(title=f"chat_ai plugin status {app}")

	return {
		"app": app,
		"plugin_name": manifest.name,
		"version": manifest.version,
		"enabled": True,
		"manifest": manifest.to_dict(),
	}


def _plugin_path(app: str) -> Path | None:
	try:
		app_path = Path(frappe.get_app_path(app))
	except Exception:
		return None
	# app_path is usually .../app_name/app_name — chat_ai_plugin sits under package root
	candidates = [
		app_path / "chat_ai_plugin",
		app_path.parent / "chat_ai_plugin",
	]
	for c in candidates:
		if c.is_dir() and (c / "__init__.py").exists():
			return c
	return None


def _plugin_subdir(app: str, name: str) -> Path | None:
	base = _plugin_path(app)
	if not base:
		return None
	sub = base / name
	return sub if sub.is_dir() else None


def _safe_settings() -> dict:
	try:
		from zatgo_core.chat_ai.erpnext.settings import get_settings_dict

		return get_settings_dict()
	except Exception:
		return {"enable_plugin_discovery": 1}


def _register_builtin_commands():
	register_commands(
		[
			{"name": "task", "label": "Tasks", "description": "Find or create tasks", "skill": "projects", "required_doctypes": ["Task"]},
			{"name": "project", "label": "Projects", "description": "Projects", "skill": "projects", "required_doctypes": ["Project"]},
			{"name": "customer", "label": "Customers", "description": "Customers", "skill": "crm", "required_doctypes": ["Customer"]},
			{"name": "invoice", "label": "Invoices", "description": "Invoices", "skill": "accounts", "required_doctypes": ["Sales Invoice"]},
			{"name": "stock", "label": "Stock", "description": "Stock / items", "skill": "inventory", "required_doctypes": ["Item"]},
			{"name": "status", "label": "Company Status", "description": "Business health snapshot", "skill": "analytics", "run_on_select": True},
			{"name": "help", "label": "Help", "description": "Show commands", "run_on_select": True},
		]
	)
