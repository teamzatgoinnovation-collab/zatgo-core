"""ZG Setting Section — navigation node under a registered application."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ZGSettingSection(Document):
    """Settings tree node for the configuration center."""

    def validate(self) -> None:
        if not self.application:
            frappe.throw(frappe._("Application is required"))
        if not self.section_key:
            frappe.throw(frappe._("Section Key is required"))
        exists = frappe.db.exists(
            "ZG Setting Section",
            {
                "application": self.application,
                "section_key": self.section_key,
                "name": ("!=", self.name),
            },
        )
        if exists:
            frappe.throw(
                frappe._("Section Key {0} already exists for this application").format(
                    self.section_key
                )
            )
