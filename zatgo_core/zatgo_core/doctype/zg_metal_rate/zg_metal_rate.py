"""ZG Metal Rate -- daily rate per gram of a metal and purity (Jewellery industry)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ZGMetalRate(Document):
    def validate(self) -> None:
        if (self.rate_per_gram or 0) <= 0:
            frappe.throw(_("Rate per Gram must be greater than zero"))
