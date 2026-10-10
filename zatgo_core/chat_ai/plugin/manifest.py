"""PluginManifest — validate chat_ai_plugin packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginManifest:
	name: str
	app: str
	version: str = "0.0.0"
	description: str = ""
	required_chat_ai_version: str = ""
	skills: list[str] = field(default_factory=list)
	provides_tools: bool = True
	provides_prompts: bool = False
	provides_knowledge: bool = False
	provides_permissions: bool = False
	provides_status_sections: bool = False
	raw: dict = field(default_factory=dict)

	def to_dict(self) -> dict:
		return {
			"name": self.name,
			"app": self.app,
			"version": self.version,
			"description": self.description,
			"required_chat_ai_version": self.required_chat_ai_version,
			"skills": self.skills,
			"provides_tools": self.provides_tools,
			"provides_prompts": self.provides_prompts,
			"provides_knowledge": self.provides_knowledge,
			"provides_permissions": self.provides_permissions,
			"provides_status_sections": self.provides_status_sections,
		}


def validate_manifest(data: dict | None, *, app: str) -> PluginManifest:
	data = data or {}
	name = (data.get("name") or data.get("plugin_name") or f"{app}_plugin").strip()
	if not name:
		raise ValueError("Plugin manifest requires name")
	version = str(data.get("version") or "0.0.0")
	req = str(data.get("required_chat_ai_version") or "").strip()
	if req:
		_assert_version_ok(req)
	return PluginManifest(
		name=name,
		app=app,
		version=version,
		description=str(data.get("description") or ""),
		required_chat_ai_version=req,
		skills=list(data.get("skills") or []),
		provides_tools=bool(data.get("provides_tools", True)),
		provides_prompts=bool(data.get("provides_prompts", False)),
		provides_knowledge=bool(data.get("provides_knowledge", False)),
		provides_permissions=bool(data.get("provides_permissions", False)),
		provides_status_sections=bool(data.get("provides_status_sections", False)),
		raw=dict(data),
	)


def _assert_version_ok(required: str) -> None:
	"""Enforce required_chat_ai_version when set (semver-ish >= check)."""
	from zatgo_core.chat_ai import __version__ as current

	req = required.lstrip(">=").strip()
	if not req:
		return
	if _version_tuple(current) < _version_tuple(req):
		raise ValueError(f"Chat AI {current} < required {req}")


def _version_tuple(v: str) -> tuple:
	parts = []
	for p in (v or "0").split("."):
		try:
			parts.append(int("".join(c for c in p if c.isdigit()) or "0"))
		except Exception:
			parts.append(0)
	while len(parts) < 3:
		parts.append(0)
	return tuple(parts[:3])


def parse_manifest_module(mod: Any, *, app: str) -> PluginManifest:
	if hasattr(mod, "get_manifest") and callable(mod.get_manifest):
		data = mod.get_manifest() or {}
	elif hasattr(mod, "MANIFEST"):
		data = getattr(mod, "MANIFEST") or {}
	else:
		data = {"name": f"{app}_plugin", "version": "0.0.0"}
	if not isinstance(data, dict):
		data = {"name": f"{app}_plugin"}
	return validate_manifest(data, app=app)
