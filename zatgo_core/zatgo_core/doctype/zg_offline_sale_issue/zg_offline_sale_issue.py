"""ZG Offline Sale Issue -- a counter sale the POS made offline and the server posted late, where something no longer matched
(price, tax, stock, item, discount cap, a very late arrival). Opened by services/offline_sale.py at sync; a manager reviews it
here. The sale itself is already posted at the server's figures: nothing on the invoice is edited, a correction is a return or
credit note."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ZGOfflineSaleIssue(Document):
    def validate(self) -> None:
        if self.status == "Reviewed" and not self.reviewed_by:
            self.reviewed_by = frappe.session.user
            self.reviewed_on = now_datetime()
        if self.status == "Open":
            self.reviewed_by = None
            self.reviewed_on = None
