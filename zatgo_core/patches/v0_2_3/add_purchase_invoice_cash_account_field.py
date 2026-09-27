"""Explicit Cash Account selector for Purchase Invoice.

Mirrors patches/v0_2_2/add_cash_account_field.py (Sales Invoice). A
company can run more than one till/cash account, so a single Mode of
Payment default isn't always enough -- this lets the user pick exactly
which Cash account pays the supplier when Payment Type = Cash. See
zatgo_core.services.invoice_cash_payment_service for how it's consumed.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Purchase Invoice"):
        return
    create_custom_fields(
        {
            "Purchase Invoice": [
                {
                    "fieldname": "custom_cash_account",
                    "label": "Cash Account",
                    "fieldtype": "Link",
                    "options": "Account",
                    "insert_after": "custom_payment_type",
                    "depends_on": 'eval:doc.custom_payment_type=="Cash"',
                    "mandatory_depends_on": 'eval:doc.custom_payment_type=="Cash"',
                    "translatable": 0,
                },
            ],
        },
        update=True,
    )
    frappe.db.commit()
