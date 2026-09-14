"""Presentation-layer computed fields for the print_designer Sales Invoice
and Quotation formats, plus a per-document signature.

print_designer's canvas binds each element to a real, stored field (its
JS runtime resolves the value directly, not arbitrary Jinja) -- values
previously computed inline in the classic Jinja template (VanSale Tax
Invoice's per-line VAT split, amount-in-words, previous/closing balance)
now need a stored home. The computation itself is unchanged from
setup/ensure_print_formats.py's existing Jinja -- see events/print_fields.py.
Mirrors zatca_integration's identical addition on kasibasia
(patches/v0_5_1/add_print_computed_fields.py).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    fields = {
        "Sales Invoice Item": [
            {
                "fieldname": "vansale_line_vat_rate",
                "label": "VAT Rate (Print)",
                "fieldtype": "Percent",
                "insert_after": "net_amount",
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "vansale_line_vat_amount",
                "label": "VAT Amount (Print)",
                "fieldtype": "Currency",
                "options": "currency",
                "insert_after": "vansale_line_vat_rate",
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "vansale_line_total_incl_vat",
                "label": "Total Incl. VAT (Print)",
                "fieldtype": "Currency",
                "options": "currency",
                "insert_after": "vansale_line_vat_amount",
                "no_copy": 1,
                "print_hide": 1,
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "vansale_authorized_signature",
                "label": "Authorized Signature",
                "fieldtype": "Signature",
                "insert_after": "remarks",
                "print_hide": 0,
                "no_copy": 1,
            },
            {
                "fieldname": "vansale_print_details_section",
                "label": "Print Details (Computed)",
                "fieldtype": "Section Break",
                "insert_after": "vansale_authorized_signature",
                "collapsible": 1,
            },
            {
                "fieldname": "vansale_amount_in_words_print",
                "label": "Amount in Words (Print)",
                "fieldtype": "Data",
                "insert_after": "vansale_print_details_section",
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "vansale_previous_balance",
                "label": "Previous Balance (Print)",
                "fieldtype": "Currency",
                "options": "currency",
                "insert_after": "vansale_amount_in_words_print",
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "vansale_new_balance",
                "label": "New Balance (Print)",
                "fieldtype": "Currency",
                "options": "currency",
                "insert_after": "vansale_previous_balance",
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "vansale_watermark_text",
                "label": "Watermark Text (Print)",
                "fieldtype": "Data",
                "insert_after": "vansale_new_balance",
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "vansale_qr_image",
                "label": "QR Image (Print)",
                "fieldtype": "Signature",
                "insert_after": "vansale_watermark_text",
                "no_copy": 1,
                "print_hide": 1,
                "description": "Stores the rendered QR PNG as a data URI so print_designer's image-binding can display it -- reuses the Signature fieldtype's existing auto-render-as-<img> behavior; not an actual signature.",
            },
        ],
    }
    filtered = {dt: defs for dt, defs in fields.items() if frappe.db.exists("DocType", dt)}
    if filtered:
        create_custom_fields(filtered, update=True)
        frappe.db.commit()
