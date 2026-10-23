# Copyright (c) 2026, ZatGo Innovation and contributors
# License: MIT

import frappe
from frappe.model.document import Document


class AIMCPServer(Document):
	def validate(self):
		# Where a tool may call is checked when it is saved, and again on every call (core/tool_sources/net.py).
		from zatgo_core.chat_ai.core.tool_sources.net import ToolNetworkError, check_configured_url

		try:
			check_configured_url(self.url, template=False)
		except ToolNetworkError as exc:
			frappe.throw(str(exc))

	@frappe.whitelist()
	def discover_tools(self):
		"""Refresh discovered_tools from the MCP endpoint."""
		frappe.only_for(("System Manager", "Chat AI Manager"))
		from zatgo_core.chat_ai.core.tool_sources.mcp import refresh_discovered_tools

		tools = refresh_discovered_tools(self.name)
		return {"count": len(tools), "tools": tools}

	@frappe.whitelist()
	def test_connection(self):
		frappe.only_for(("System Manager", "Chat AI Manager"))
		from zatgo_core.chat_ai.core.tool_sources.health import test_mcp_server

		return test_mcp_server(self.name, persist=True)
