"""Skill discovery — load skill packages from filesystem manifests (no Frappe)."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zatgo_core.chat_ai.core.tool_router.spec import ToolSpec


@dataclass
class SkillSpec:
	name: str
	label: str = ""
	description: str = ""
	required_doctypes: list[str] = field(default_factory=list)
	required_apps: list[str] = field(default_factory=list)
	path: str = ""
	prompt: str = ""
	examples: str = ""
	tools: list[ToolSpec] = field(default_factory=list)
	enabled: bool = True


_SKILLS: dict[str, SkillSpec] = {}
_EXTRA_ROOTS: list[str] = []


def add_skill_root(path: str):
	if path and path not in _EXTRA_ROOTS:
		_EXTRA_ROOTS.append(path)


def register_skill(spec: SkillSpec | str):
	if isinstance(spec, str):
		# dotted module with register()
		mod = importlib.import_module(spec)
		fn = getattr(mod, "register", None)
		if not callable(fn):
			raise ValueError(f"{spec} has no register()")
		spec = fn()
	_SKILLS[spec.name] = spec
	return spec


def get_skill(name: str) -> SkillSpec | None:
	return _SKILLS.get(name)


def list_skills() -> list[SkillSpec]:
	return list(_SKILLS.values())


def clear_skills():
	_SKILLS.clear()


def discover(roots: list[str] | None = None, *, doctype_exists=None, app_installed=None) -> list[SkillSpec]:
	"""Scan roots for skill packages. Optional callables gate required_doctypes/apps."""
	doctype_exists = doctype_exists or (lambda d: True)
	app_installed = app_installed or (lambda a: True)
	found: list[SkillSpec] = []
	scan_roots = list(roots or []) + list(_EXTRA_ROOTS)
	for root in scan_roots:
		root_path = Path(root)
		if not root_path.is_dir():
			continue
		for child in sorted(root_path.iterdir()):
			if not child.is_dir() or child.name.startswith("_"):
				continue
			# integrations: load parent package (if skill.yaml) plus nested connector skills
			if child.name == "integrations":
				parent = _load_skill_dir(child)
				if parent:
					found.append(parent)
				for integ in sorted(child.iterdir()):
					if integ.is_dir() and not integ.name.startswith("_"):
						spec = _load_skill_dir(integ)
						if spec:
							found.append(spec)
				continue
			spec = _load_skill_dir(child)
			if spec:
				found.append(spec)

	for spec in found:
		if any(not doctype_exists(d) for d in spec.required_doctypes):
			spec.enabled = False
		if any(not app_installed(a) for a in spec.required_apps):
			spec.enabled = False
		if spec.enabled:
			_SKILLS[spec.name] = spec
	return [s for s in found if s.enabled]


def _load_skill_dir(path: Path) -> SkillSpec | None:
	manifest = path / "manifest.py"
	skill_py = path / "skill.py"
	name = path.name
	label = name.replace("_", " ").title()
	description = ""
	required_doctypes: list[str] = []
	required_apps: list[str] = []
	tools: list[ToolSpec] = []

	# Try skill.yaml
	yaml_path = path / "skill.yaml"
	if yaml_path.exists():
		data = _parse_simple_yaml(yaml_path.read_text())
		name = data.get("name") or name
		label = data.get("label") or label
		description = data.get("description") or ""
		required_doctypes = _as_list(data.get("required_doctypes"))
		required_apps = _as_list(data.get("required_apps"))

	if manifest.exists():
		mod = _load_module(f"chat_ai_skill_manifest_{path.name}", manifest)
		meta = getattr(mod, "MANIFEST", None) or getattr(mod, "manifest", None)
		if callable(getattr(mod, "get_manifest", None)):
			meta = mod.get_manifest()
		if isinstance(meta, dict):
			name = meta.get("name") or name
			label = meta.get("label") or label
			description = meta.get("description") or description
			required_doctypes = meta.get("required_doctypes") or required_doctypes
			required_apps = meta.get("required_apps") or required_apps

	if skill_py.exists():
		mod = _load_module(f"chat_ai_skill_{path.name}", skill_py)
		if callable(getattr(mod, "register", None)):
			spec = mod.register()
			if isinstance(spec, SkillSpec):
				spec.path = str(path)
				_load_prompt_examples(spec, path)
				return spec

	tools_py = path / "tools.py"
	if tools_py.exists():
		mod = _load_module(f"chat_ai_tools_{path.name}", tools_py)
		if callable(getattr(mod, "get_tools", None)):
			tools = list(mod.get_tools() or [])
		elif callable(getattr(mod, "TOOLS", None)):
			tools = list(mod.TOOLS)
		elif isinstance(getattr(mod, "TOOLS", None), list):
			tools = list(mod.TOOLS)

	# tool.yaml files
	tools_dir = path / "tools"
	if tools_dir.is_dir():
		for yml in tools_dir.glob("*.yaml"):
			tools.append(_tool_from_yaml(yml, skill=name))
		for yml in tools_dir.glob("*.tool.yaml"):
			tools.append(_tool_from_yaml(yml, skill=name))

	spec = SkillSpec(
		name=name,
		label=label,
		description=description,
		required_doctypes=list(required_doctypes),
		required_apps=list(required_apps),
		path=str(path),
		tools=tools,
	)
	_load_prompt_examples(spec, path)
	return spec


def _load_prompt_examples(spec: SkillSpec, path: Path):
	for fname, attr in (("prompt.md", "prompt"), ("examples.md", "examples"), ("prompt.py", None)):
		fp = path / fname
		if not fp.exists():
			continue
		if fname.endswith(".md"):
			setattr(spec, attr, fp.read_text())
		elif fname == "prompt.py":
			mod = _load_module(f"chat_ai_prompt_{path.name}", fp)
			if hasattr(mod, "PROMPT"):
				spec.prompt = str(mod.PROMPT)


def _tool_from_yaml(path: Path, skill: str) -> ToolSpec:
	data = _parse_simple_yaml(path.read_text())
	return ToolSpec(
		name=str(data.get("name") or path.stem.replace(".tool", "")),
		description=str(data.get("description") or ""),
		category=str(data.get("category") or "read"),
		skill=skill,
		confirmation_required=bool(data.get("confirmation_required")),
		supported_doctypes=_as_list(data.get("supported_doctypes")),
		required_doctypes=_as_list(data.get("required_doctypes") or data.get("supported_doctypes")),
		examples=_as_list(data.get("examples")),
		permissions=_as_list(data.get("permissions")),
		parameters=data.get("parameters") if isinstance(data.get("parameters"), dict) else {},
		source=str(data.get("source") or "python"),
	)


def _load_module(name: str, path: Path):
	spec = importlib.util.spec_from_file_location(name, path)
	mod = importlib.util.module_from_spec(spec)
	sys.modules[name] = mod
	assert spec.loader
	spec.loader.exec_module(mod)
	return mod


def _as_list(val: Any) -> list:
	if val is None:
		return []
	if isinstance(val, list):
		return val
	if isinstance(val, str):
		return [v.strip() for v in val.split(",") if v.strip()]
	return list(val)


def _parse_simple_yaml(text: str) -> dict:
	"""Minimal YAML subset (key: value, lists with -). Avoid PyYAML dependency."""
	try:
		import yaml  # type: ignore

		return yaml.safe_load(text) or {}
	except Exception:
		pass
	data: dict[str, Any] = {}
	current_list_key = None
	for line in text.splitlines():
		raw = line.rstrip()
		if not raw or raw.strip().startswith("#"):
			continue
		if raw.strip().startswith("- ") and current_list_key:
			data.setdefault(current_list_key, []).append(raw.strip()[2:].strip().strip("\"'"))
			continue
		if ":" in raw:
			key, _, val = raw.partition(":")
			key = key.strip()
			val = val.strip().strip("\"'")
			if val == "":
				current_list_key = key
				data[key] = []
			elif val.startswith("[") and val.endswith("]"):
				inner = val[1:-1]
				data[key] = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
				current_list_key = None
			else:
				if val.lower() in ("true", "yes"):
					data[key] = True
				elif val.lower() in ("false", "no"):
					data[key] = False
				else:
					data[key] = val
				current_list_key = None
	return data
