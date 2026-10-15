"""ZG Gym Plan -- a membership plan (Gym industry)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ZGGymPlan(Document):
    def validate(self) -> None:
        if (self.duration_days or 0) <= 0:
            frappe.throw(_("Duration must be at least 1 day"))
        if (self.price or 0) < 0:
            frappe.throw(_("Price cannot be negative"))
