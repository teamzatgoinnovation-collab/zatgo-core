"""'Offline Receipt No.' on Sales Invoice: the number the POS printed on the receipt of a sale it made without a connection
(services/offline_sale.py). The invoice itself is numbered by the server when the sale is posted, so a manager can match
the paper receipt to the invoice. Additive, indexed, read only. Re-run on every migrate (setup/ensure_custom_fields.py)."""

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
                    "fieldname": "zg_offline_receipt",
                    "label": "Offline Receipt No.",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "no_copy": 1,
                    "search_index": 1,
                    "print_hide": 1,
                    "insert_after": "zatgo_client_id",
                    "description": "Receipt number printed by the POS while it was offline.",
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
