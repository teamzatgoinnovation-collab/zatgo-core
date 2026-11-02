"""ZG Duplicate Prevention Settings controller -- global switches for services/duplicate."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class ZGDuplicatePreventionSettings(Document):
    def validate(self) -> None:
        if not 1 <= cint(self.result_limit) <= 25:
            frappe.throw("Results per Lookup must be between 1 and 25.")
        if not 50 <= flt(self.fuzzy_threshold) <= 100:
            frappe.throw("Fuzzy Name Threshold must be between 50 and 100 percent.")
        if cint(self.scan_limit) < 0:
            frappe.throw("Scan limit cannot be negative.")

    def on_update(self) -> None:
        from zatgo_core.services.duplicate import config

        config.clear_cache()
