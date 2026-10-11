"""zatgo_client_id on Purchase Order, for VanSaleX purchase orders.

Same idempotency key as Sales Order / Purchase Invoice (DB-unique, so a
retried create can't make a second order -- see services/idempotency.py).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Purchase Order"):
        return
    create_custom_fields(
        {
            "Purchase Order": [
                {
                    "fieldname": "zatgo_client_id",
                    "label": "ZatGo Client Id",
                    "fieldtype": "Data",
                    "insert_after": "supplier",
                    "unique": 1,
                    "read_only": 1,
                    "no_copy": 1,
                    "translatable": 0,
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
