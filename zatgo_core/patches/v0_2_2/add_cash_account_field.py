"""Explicit Cash Account selector for Sales Invoice.

A company can run more than one till/cash account, so a single Mode of
Payment default (patches/v0_2_2/add_payment_type_field.py's original
fallback) isn't always enough -- this lets the user pick exactly which
Cash account receives the payment when Payment Type = Cash. See
zatgo_core.services.sales_invoice_payment_service for how it's consumed
(preferred over the Mode of Payment default when set).
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
