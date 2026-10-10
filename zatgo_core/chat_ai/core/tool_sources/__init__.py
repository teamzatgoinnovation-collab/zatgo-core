"""External tool sources (REST, MCP, integrations)."""

from __future__ import annotations

from zatgo_core.chat_ai.core.tool_router.spec import ToolSpec


def load_external_tools(settings: dict | None = None) -> list[ToolSpec]:
	"""Load enabled REST / MCP / integration tools based on Chat AI Settings flags."""
	settings = settings or {}
	tools: list[ToolSpec] = []
	if settings.get("enable_rest_tools"):
		try:
			from zatgo_core.chat_ai.core.tool_sources.rest import load_rest_tools

			tools.extend(load_rest_tools())
		except Exception:
			pass
	if settings.get("enable_mcp_tools"):
		try:
			from zatgo_core.chat_ai.core.tool_sources.mcp import load_mcp_tools

			tools.extend(load_mcp_tools())
		except Exception:
			pass
	if settings.get("enable_integrations"):
		try:
			from zatgo_core.chat_ai.core.tool_sources.integrations import load_integration_tools

			tools.extend(load_integration_tools())
		except Exception:
			pass
	return tools
