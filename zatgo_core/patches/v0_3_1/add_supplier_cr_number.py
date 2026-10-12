"""CR Number on Supplier, mirroring the Customer field (zatgo_cr_number)."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Supplier"):
        return
    create_custom_fields(
        {
            "Supplier": [
                {
                    "fieldname": "zatgo_cr_number",
                    "label": "CR Number",
                    "fieldtype": "Data",
                    "insert_after": "tax_id",
                    "translatable": 0,
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
