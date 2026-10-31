"""ZG POS Settings controller -- site-wide defaults for the ZatGo POS desktop app.
The values reach the POS through zatgo_core.services.pos_settings.effective()
(API: zatgo_core.api.v1.pos_settings.get)."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt

from zatgo_core.services import app_authority, pos_settings


class ZGPOSSettings(Document):
    def onload(self) -> None:
        # A site that never chose a type shows the one its industries imply, not a blank.
        if not self.pos_type:
            self.pos_type = pos_settings.derived_type()

    def validate(self) -> None:
        self._validate_pos_type()
        if not 0 <= flt(self.max_discount_percent) <= 100:
            frappe.throw("Max Discount % must be between 0 and 100.")
        if cint(self.print_copies) < 1:
            frappe.throw("Receipt Copies must be at least 1.")
        for field, label, low, high in (
            ("max_offline_hours", "Longest Offline Period", 1, 720),
            ("max_pending_sales", "Most Sales Waiting on a Device", 1, 5000),
            ("snapshot_refresh_minutes", "Refresh Items and Prices Every", 1, 1440),
        ):
            value = cint(self.get(field))
            if value and not low <= value <= high:
                frappe.throw(f"{label} must be between {low} and {high}.")
        if self.default_payment_mode and not frappe.db.get_value("Mode of Payment", self.default_payment_mode, "enabled"):
            frappe.throw("Default Mode of Payment must be an enabled Mode of Payment.")

    def _validate_pos_type(self) -> None:
        if self.pos_type in pos_settings.COMING_SOON:
            frappe.throw(f"{self.pos_type.split(' (')[0]} is not available yet.")
        # No choice stays "no choice" (the industries keep deciding); only a picked type is stored.
        before = self.get_doc_before_save()
        was = (before.pos_type if before else None) or pos_settings.derived_type()
        self.flags.pos_type_changed = bool(self.pos_type) and self.pos_type != was
        # Choosing a type may switch an industry on, so it is the same call as switching one.
        if self.flags.pos_type_changed and not app_authority.is_system_context() and not app_authority.can_switch():
            frappe.throw("Only a System Manager can change the POS Type.", frappe.PermissionError)

    def on_update(self) -> None:
        if self.flags.pos_type_changed:
            pos_settings.switch_industry_on(self.pos_type)
