"""Add Quotation Item.zatgo_billing_type — a plain label field (e.g.
"One-time", "Annually") for the quotation print format's "Type" column.
Not a link to UOM: billing frequency isn't a unit of measure, and forcing
it through UOM would pollute that shared master with non-unit values.

Also invoked directly from zatgo_core.setup.ensure_custom_fields (see that
module's docstring for why patches.txt alone isn't relied on for this).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    fields = {
        "Quotation Item": [
            {
                "fieldname": "zatgo_billing_type",
                "label": "Type",
                "fieldtype": "Data",
                "insert_after": "description",
                "no_copy": 0,
                "translatable": 0,
            }
        ],
    }
    filtered = {dt: defs for dt, defs in fields.items() if frappe.db.exists("DocType", dt)}
    if filtered:
        create_custom_fields(filtered, update=True)
        frappe.db.commit()
