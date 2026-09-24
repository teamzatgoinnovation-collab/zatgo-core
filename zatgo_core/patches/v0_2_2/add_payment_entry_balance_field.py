"""Read-only Party Balance display field on Payment Entry.

Shows the selected party's live outstanding balance right on the form
(populated by public/js/payment_entry.js via
zatgo_core.api.v1.accounting.payments.party_balance) instead of a
transient dashboard alert -- a plain Data field, never written to by
anything but that client script, so it's a display snapshot, not a
second source of truth for the party's real balance.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Payment Entry"):
        return
    create_custom_fields(
        {
            "Payment Entry": [
                {
                    "fieldname": "custom_party_balance",
                    "label": "Party Balance",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "no_copy": 1,
                    "insert_after": "party_name",
                    "depends_on": "eval:doc.party && doc.company && in_list(['Customer','Supplier'], doc.party_type)",
                    "translatable": 0,
                },
            ],
        },
        update=True,
    )
    frappe.db.commit()
