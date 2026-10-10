# Copyright (c) 2026, ZatGo Innovation and contributors

import frappe
from frappe.model.document import Document


class TrackerActivitySession(Document):
	def validate(self):
		if self.status == "Running":
			others = frappe.db.count(
				"Tracker Activity Session",
				{
					"user": self.user,
					"status": "Running",
					"name": ("!=", self.name or ""),
				},
			)
			if others:
				frappe.throw("Only one Running activity session is allowed per user.")
