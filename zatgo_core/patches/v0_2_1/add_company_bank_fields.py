"""Company bank-account fields for the print_designer Sales Invoice.

Displays the seller's bank details for customer wire transfers, matching
the bilingual invoice reference layout. Two slots (most Saudi trading
companies show two accounts). Mirrors zatca_integration's identical
addition on kasibasia (patches/v0_5_0/add_company_bank_fields.py) --
independent field set per app, no shared code, per the one-repo-per-app
convention.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Company"):
        return
    create_custom_fields(
        {
            "Company": [
                {
                    "fieldname": "vansale_bank_details_section",
                    "label": "Invoice Bank Details",
                    "fieldtype": "Section Break",
                    "insert_after": "registration_details",
                    "collapsible": 1,
                },
                {
                    "fieldname": "vansale_bank_1_name",
                    "label": "Bank 1 Name",
                    "fieldtype": "Data",
                    "insert_after": "vansale_bank_details_section",
                    "translatable": 0,
                },
                {
                    "fieldname": "vansale_bank_1_account",
                    "label": "Bank 1 Account Number",
                    "fieldtype": "Data",
                    "insert_after": "vansale_bank_1_name",
                    "translatable": 0,
                },
                {
                    "fieldname": "vansale_bank_1_iban",
                    "label": "Bank 1 IBAN",
                    "fieldtype": "Data",
                    "insert_after": "vansale_bank_1_account",
                    "translatable": 0,
                },
                {
                    "fieldname": "vansale_bank_column_break",
                    "fieldtype": "Column Break",
                    "insert_after": "vansale_bank_1_iban",
                },
                {
                    "fieldname": "vansale_bank_2_name",
                    "label": "Bank 2 Name",
                    "fieldtype": "Data",
                    "insert_after": "vansale_bank_column_break",
                    "translatable": 0,
                },
                {
                    "fieldname": "vansale_bank_2_account",
                    "label": "Bank 2 Account Number",
                    "fieldtype": "Data",
                    "insert_after": "vansale_bank_2_name",
                    "translatable": 0,
                },
                {
                    "fieldname": "vansale_bank_2_iban",
                    "label": "Bank 2 IBAN",
                    "fieldtype": "Data",
                    "insert_after": "vansale_bank_2_account",
                    "translatable": 0,
                },
            ],
        },
        update=True,
    )
    frappe.db.commit()
