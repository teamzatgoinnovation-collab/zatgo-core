"""Ensure zatgo_client_id custom fields for VanSale idempotency."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    fields = {
        "Sales Invoice": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "customer",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
        "Sales Order": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "customer",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
        "Payment Entry": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "party",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
        "Stock Entry": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "stock_entry_type",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
        # unique: 1 like every other doctype here — a ZG Trip is created by
        # the mobile client with a client-generated id, so it needs the same
        # DB-level duplicate protection (see .claude/rules/accounting.md).
        # v0_2_0.make_zg_trip_client_id_unique dedupes existing rows and
        # materializes the index on sites created before this was fixed.
        "ZG Trip": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "status",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
    }
    # Only create for DocTypes that exist
    filtered = {dt: defs for dt, defs in fields.items() if frappe.db.exists("DocType", dt)}
    if filtered:
        create_custom_fields(filtered, update=True)
        frappe.db.commit()
