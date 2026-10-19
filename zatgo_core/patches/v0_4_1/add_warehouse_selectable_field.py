"""'Selectable' checkbox on Warehouse: which warehouses the warehouse dropdowns
(sales/purchase forms, VanSaleX picker) offer. The fieldname keeps its original
zg_vansalex_ prefix so no data has to move."""

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
                    "fieldname": "zg_vansalex_selectable",
                    "label": "Selectable Warehouse",
                    "fieldtype": "Check",
                    "default": "0",
                    "insert_after": "disabled",
                    "description": "Offer this warehouse in warehouse dropdowns (sales/purchase forms, VanSaleX). When none is ticked, all are offered.",
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
