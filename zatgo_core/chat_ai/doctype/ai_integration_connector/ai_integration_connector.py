# Copyright (c) 2026, ZatGo Innovation and contributors
# License: MIT

import frappe
from frappe.model.document import Document


class AIIntegrationConnector(Document):
	@frappe.whitelist()
	def test_connection(self):
		frappe.only_for(("System Manager", "Chat AI Manager"))
		from zatgo_core.chat_ai.core.tool_sources.health import test_integration

		return test_integration(self.name, persist=True)
