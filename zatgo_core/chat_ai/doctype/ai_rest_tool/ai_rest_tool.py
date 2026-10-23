# Copyright (c) 2026, ZatGo Innovation and contributors
# License: MIT

import frappe
from frappe.model.document import Document


class AIRESTTool(Document):
	def validate(self):
		# Where a tool may call is checked when it is saved, and again on every call (core/tool_sources/net.py).
		from zatgo_core.chat_ai.core.tool_sources.net import ToolNetworkError, check_configured_url

		try:
			check_configured_url(self.url_template, template=True)
		except ToolNetworkError as exc:
			frappe.throw(str(exc))

	@frappe.whitelist()
	def test_connection(self):
		frappe.only_for(("System Manager", "Chat AI Manager"))
		from zatgo_core.chat_ai.core.tool_sources.health import test_rest_tool

		return test_rest_tool(self.name, persist=True)
