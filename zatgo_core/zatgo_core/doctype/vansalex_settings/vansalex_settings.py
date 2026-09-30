"""VanSaleX Settings controller — company-wide defaults for the VanSaleX
mobile app. Per-user overrides live on ZG Van Sale Profile; the effective
values are resolved by zatgo_core.services.vansalex_settings.resolve()."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class VanSaleXSettings(Document):
    def validate(self) -> None:
        if not 0 <= flt(self.max_discount_percent) <= 100:
            frappe.throw("Max Discount % must be between 0 and 100.")
        if self.default_payment_type == "Credit" and not self.allow_credit_sales:
            frappe.throw("Default Payment Type can't be Credit while credit sales are not allowed.")
