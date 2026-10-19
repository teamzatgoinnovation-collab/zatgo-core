"""'Selectable in VanSaleX' checkbox on Warehouse: which warehouses the
VanSaleX Source Warehouse picker offers (see services/vansalex_settings.py)."""

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
                    "label": "Selectable in VanSaleX",
                    "fieldtype": "Check",
                    "default": "0",
                    "insert_after": "disabled",
                    "description": "Offer this warehouse in the VanSaleX Source Warehouse picker.",
                }
            ],
        },
        update=True,
    )
    frappe.db.commit()
