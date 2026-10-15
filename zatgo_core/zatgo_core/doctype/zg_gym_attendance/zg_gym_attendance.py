"""ZG Gym Attendance -- a check-in against an active membership (Gym industry)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ZGGymAttendance(Document):
    def validate(self) -> None:
        end_date, status = frappe.db.get_value("ZG Gym Membership", self.membership, ["end_date", "status"])
        if status == "Cancelled" or getdate(self.check_in) > getdate(end_date):
            frappe.throw(_("Membership {0} is not active on {1}").format(self.membership, getdate(self.check_in)))
        if self.check_out and self.check_out < self.check_in:
            frappe.throw(_("Check Out cannot be before Check In"))
