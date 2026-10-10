"""Integrations skill — tools are loaded dynamically from Chat AI connectors."""

from __future__ import annotations

from zatgo_core.chat_ai.core.tool_router.spec import ToolSpec


def get_tools() -> list[ToolSpec]:
	# Connector tools are merged via collect_tools / load_external_tools.
	# Keep an empty list here so discovery still registers the skill prompt.
	return []
