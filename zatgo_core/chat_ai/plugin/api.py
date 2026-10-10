"""Platform SDK — register_* APIs for external apps."""

from __future__ import annotations

from typing import Any, Callable

from zatgo_core.chat_ai.core.skills import SkillSpec, add_skill_root, register_skill as _register_skill
from zatgo_core.chat_ai.core.tool_router.spec import ToolSpec

_TOOLS: dict[str, ToolSpec] = {}
_CONTEXT_PROVIDERS: list[Callable] = []
_PROMPTS: dict[str, dict] = {}
_EVENTS: dict[str, Any] = {}
_COMMANDS: dict[str, dict] = {}
_UI_ACTIONS: list[dict] = []
_SIDEBAR_WIDGETS: list[dict] = []


def register_tools(tools: list[ToolSpec] | Callable):
	if callable(tools) and not isinstance(tools, list):
		tools = tools()
	for t in tools or []:
		if isinstance(t, ToolSpec):
			_TOOLS[t.name] = t
	return list(_TOOLS.values())


def register_skill(skill: SkillSpec | str):
	return _register_skill(skill)


def register_context(provider: Callable):
	_CONTEXT_PROVIDERS.append(provider)
	return provider


def register_prompt(prompt: dict):
	name = prompt.get("name") or f"prompt_{len(_PROMPTS)}"
	_PROMPTS[name] = prompt
	return name


def register_events(handlers: dict):
	_EVENTS.update(handlers or {})
	return _EVENTS


def register_commands(commands: list[dict]):
	for c in commands or []:
		name = (c.get("name") or "").lstrip("/")
		if name:
			_COMMANDS[name] = c
	return list(_COMMANDS.values())


def register_ui_actions(actions: list[dict]):
	_UI_ACTIONS.extend(actions or [])
	return _UI_ACTIONS


def register_sidebar_widgets(widgets: list[dict]):
	_SIDEBAR_WIDGETS.extend(widgets or [])
	return _SIDEBAR_WIDGETS


def get_registered_tools() -> list[ToolSpec]:
	return list(_TOOLS.values())


def get_commands() -> list[dict]:
	return list(_COMMANDS.values())


def get_context_providers() -> list[Callable]:
	return list(_CONTEXT_PROVIDERS)


def get_ui_actions() -> list[dict]:
	return list(_UI_ACTIONS)


def get_sidebar_widgets() -> list[dict]:
	return list(_SIDEBAR_WIDGETS)


def register_skill_path(path: str):
	add_skill_root(path)
