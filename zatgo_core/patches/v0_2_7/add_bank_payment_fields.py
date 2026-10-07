"""Bank Account + Bank Reference No on Sales Invoice, for Payment Type = Bank.

Payment Type "Bank" (patches/v0_2_2/add_payment_type_field.py) works like
Cash: on submit zatgo_core.services.invoice_cash_payment_service creates and
submits the Payment Entry -- into the Bank-type account picked here instead
of a Cash account. ERPNext requires a reference no. and date on every bank
Payment Entry; the reference is the transfer / cheque no. entered here, or
the invoice number when left blank, and the date is the invoice's posting date.
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
                    "fieldname": "custom_bank_account",
                    "label": "Bank Account",
                    "fieldtype": "Link",
                    "options": "Account",
                    "insert_after": "custom_cash_account",
                    "depends_on": 'eval:doc.custom_payment_type=="Bank"',
                    "mandatory_depends_on": 'eval:doc.custom_payment_type=="Bank"',
                    "translatable": 0,
                },
                {
                    "fieldname": "custom_bank_reference_no",
                    "label": "Bank Reference No",
                    "fieldtype": "Data",
                    "insert_after": "custom_bank_account",
                    "depends_on": 'eval:doc.custom_payment_type=="Bank"',
                    "description": "Transfer / cheque no. Left blank, the invoice number is used.",
                    "no_copy": 1,
                    "translatable": 0,
                },
            ],
        },
        update=True,
    )
    frappe.db.commit()
