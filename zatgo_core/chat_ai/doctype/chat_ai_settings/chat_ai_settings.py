# Copyright (c) 2026, ZatGo Innovation and contributors
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document

from zatgo_core.chat_ai.core.providers import local_guard


class ChatAISettings(Document):
	def validate(self):
		self.validate_local_only()

	def validate_local_only(self):
		"""With 'Local models only' on, refuse to save a configuration that would send anything
		to an external host (the provider factory enforces the same at call time)."""
		if self.flags.get("ignore_local_only") or not local_guard.is_enabled(self.as_dict()):
			return
		settings = self.as_dict()
		problems = local_guard.check_settings(settings)
		if problems:
			frappe.throw(
				"<br>".join(problems)
				+ "<br><br>"
				+ _("Use Ollama or another server on your own network, or untick 'Local models only' to allow an external API."),
				title=_("Local models only"),
			)
