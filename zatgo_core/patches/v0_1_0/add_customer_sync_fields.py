"""Custom fields for offline customer sync (VanSale / ERPNext v16)."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    fields = {
        "Customer": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "naming_series",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_customer_name_ar",
                "label": "Customer Name Arabic",
                "fieldtype": "Data",
                "insert_after": "customer_name",
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_cr_number",
                "label": "CR Number",
                "fieldtype": "Data",
                "insert_after": "tax_id",
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_google_map_url",
                "label": "Google Map Location",
                "fieldtype": "Data",
                "insert_after": "website",
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_cr_image",
                "label": "Commercial Registration Image",
                "fieldtype": "Attach Image",
                "insert_after": "image",
            },
            {
                "fieldname": "zatgo_vat_certificate",
                "label": "VAT Certificate",
                "fieldtype": "Attach Image",
                "insert_after": "zatgo_cr_image",
            },
            {
                "fieldname": "zatgo_customer_photo",
                "label": "Customer Photo",
                "fieldtype": "Attach Image",
                "insert_after": "zatgo_vat_certificate",
            },
        ],
        "Address": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "address_title",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            },
            {
                "fieldname": "zatgo_latitude",
                "label": "Latitude",
                "fieldtype": "Float",
                "insert_after": "pincode",
            },
            {
                "fieldname": "zatgo_longitude",
                "label": "Longitude",
                "fieldtype": "Float",
                "insert_after": "zatgo_latitude",
            },
            {
                "fieldname": "zatgo_google_map_url",
                "label": "Google Map Location",
                "fieldtype": "Data",
                "insert_after": "zatgo_longitude",
                "translatable": 0,
            },
        ],
        "Contact": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "first_name",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            },
        ],
    }
    filtered = {dt: defs for dt, defs in fields.items() if frappe.db.exists("DocType", dt)}
    if filtered:
        create_custom_fields(filtered, update=True)
        frappe.db.commit()
