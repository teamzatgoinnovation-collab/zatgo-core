"""Cash / Bank / Credit payment-type selector on Sales Invoice.

Drives the auto Payment Entry creation in
zatgo_core.services.invoice_cash_payment_service -- Cash and Bank submits
create and submit a matching Payment Entry via ERPNext's own
get_payment_entry() (Bank's own fields: patches/v0_2_7/add_bank_payment_fields.py),
Credit leaves the invoice outstanding. See that module for the on_submit
logic this field feeds. Re-run on every migrate (setup/ensure_custom_fields.py),
so the options here are the live ones. (Purchase Invoice has its own mirrored field, see
patches/v0_2_3/add_purchase_invoice_payment_type_field.py.)
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Sales Invoice"):
        return
    create_custom_fields(
        {
            "Sales Invoice": [
                {
                    "fieldname": "custom_payment_type",
                    "label": "Payment Type",
                    "fieldtype": "Select",
                    "options": "\nCash\nBank\nCredit",
                    "insert_after": "due_date",
                    "translatable": 0,
                },
            ],
        },
        update=True,
    )
    frappe.db.commit()
