"""Arabic name on Supplier, mirroring the Customer field (zatgo_customer_name_ar)."""

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
                    "fieldname": "zatgo_supplier_name_ar",
                    "label": "Supplier Name Arabic",
                    "fieldtype": "Data",
                    "insert_after": "supplier_name",
                    "translatable": 0,
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
