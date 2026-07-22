"""Add Sales Invoice custom field for ZATCA Phase 2 simplified QR."""

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
                    "fieldname": "zatca_qr_base64",
                    "label": "ZATCA QR Base64",
                    "fieldtype": "Long Text",
                    "insert_after": "remarks",
                    "read_only": 1,
                    "no_copy": 1,
                    "translatable": 0,
                }
            ]
        },
        update=True,
    )
    frappe.db.commit()
