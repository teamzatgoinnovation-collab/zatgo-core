"""ZG POS Settings controller -- site-wide defaults for the ZatGo POS desktop app.
The values reach the POS through zatgo_core.services.pos_settings.effective()
(API: zatgo_core.api.v1.pos_settings.get)."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class ZGPOSSettings(Document):
    def validate(self) -> None:
        if not 0 <= flt(self.max_discount_percent) <= 100:
            frappe.throw("Max Discount % must be between 0 and 100.")
        if cint(self.print_copies) < 1:
            frappe.throw("Receipt Copies must be at least 1.")
        if self.default_payment_mode and not frappe.db.get_value("Mode of Payment", self.default_payment_mode, "enabled"):
            frappe.throw("Default Mode of Payment must be an enabled Mode of Payment.")
