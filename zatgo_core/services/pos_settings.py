"""What the ZatGo POS app is told about this site: `ZG POS Settings` as one flat dict.

Read by api/v1/pos_settings.py. Defaults are the ones in the DocType JSON, so a site that never saved the form
gets the same answer as one that saved it untouched."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

SETTINGS = "ZG POS Settings"


def effective() -> dict[str, Any]:
    doc = frappe.get_cached_doc(SETTINGS)
    allow_discounts = cint(doc.allow_discounts)
    return {
        "default_warehouse": doc.default_warehouse or None,
        "default_price_list": doc.default_price_list or None,
        "default_customer": doc.default_customer or None,
        "allow_discounts": allow_discounts,
        # No discounting means a 0 cap, whatever the stored percent says.
        "max_discount_percent": flt(doc.max_discount_percent) if allow_discounts else 0.0,
        "default_payment_mode": doc.default_payment_mode or None,
        "allow_split_payment": cint(doc.allow_split_payment),
        "receipt_header": doc.receipt_header or "",
        "receipt_footer": doc.receipt_footer or "",
        "show_tax_on_receipt": cint(doc.show_tax_on_receipt),
        "print_copies": max(cint(doc.print_copies), 1),
    }
