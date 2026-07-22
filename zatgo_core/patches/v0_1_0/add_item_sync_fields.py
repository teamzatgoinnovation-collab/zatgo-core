"""Custom fields for offline Item/product sync (VanSale / ERPNext v16)."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    fields = {
        "Item": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "item_code",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_item_name_ar",
                "label": "Item Name Arabic",
                "fieldtype": "Data",
                "insert_after": "item_name",
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_sku",
                "label": "SKU",
                "fieldtype": "Data",
                "insert_after": "zatgo_item_name_ar",
                "translatable": 0,
            },
        ],
    }
    filtered = {dt: defs for dt, defs in fields.items() if frappe.db.exists("DocType", dt)}
    if filtered:
        create_custom_fields(filtered, update=True)
        frappe.db.commit()
