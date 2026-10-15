"""ZG Gym Membership -- a member's period on a plan (Gym industry)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


class ZGGymMembership(Document):
    def validate(self) -> None:
        plan = frappe.db.get_value("ZG Gym Plan", self.plan, ["duration_days", "price", "is_active"], as_dict=True)
        if not plan or not plan.is_active:
            frappe.throw(_("Plan {0} is not active").format(self.plan))
        self.end_date = add_days(getdate(self.start_date), plan.duration_days - 1)
        if self.is_new():
            self.amount = plan.price
        if self.status != "Cancelled":
            self.status = "Active" if getdate(self.end_date) >= getdate(today()) else "Expired"
