"""'VanSaleX Transfer Point' checkbox on Warehouse: the warehouses a VanSaleX
field user may move stock to / from (their own van <-> a transfer point,
services/vansalex_stock_rules.py). None ticked = field users can't transfer."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Warehouse"):
        return
    create_custom_fields(
        {
            "Warehouse": [
                {
                    "fieldname": "zg_vansalex_transfer_point",
                    "label": "VanSaleX Transfer Point",
                    "fieldtype": "Check",
                    "default": "0",
                    "insert_after": "zg_vansalex_selectable",
                    "description": "VanSaleX drivers may transfer stock between their van and this warehouse (needs the 'Transfer stock' feature). Leave unticked on every warehouse to stop driver transfers.",
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
