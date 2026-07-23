# Copyright (c) 2026, ZatGo Innovation and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


def sales_invoice_naming_series_options() -> str:
    """Mirror Sales Invoice naming_series options (ERPNext Selling settings)."""
    try:
        field = frappe.get_meta("Sales Invoice").get_field("naming_series")
        if field and field.options:
            opts = [o.strip() for o in str(field.options).split("\n") if o.strip()]
            # Leading blank = "use DocType default"
            return "\n" + "\n".join(opts)
    except Exception:
        pass
    return "\nACC-SINV-.YYYY.-\nACC-SINV-RET-.YYYY.-"


class ZGVanSaleProfile(Document):
    def validate(self):
        # Keep Select options aligned with ERPNext Sales Invoice.
        meta_field = self.meta.get_field("sales_invoice_naming_series")
        if meta_field:
            meta_field.options = sales_invoice_naming_series_options()

        series = (self.sales_invoice_naming_series or "").strip()
        if not series:
            return
        allowed = {
            o.strip()
            for o in sales_invoice_naming_series_options().split("\n")
            if o.strip()
        }
        if series not in allowed:
            frappe.throw(
                f"Naming series '{series}' is not configured on Sales Invoice. "
                "Add it under Selling → Sales Invoice (Naming Series) in ERPNext.",
                frappe.ValidationError,
            )
