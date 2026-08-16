"""Ensure zatgo_client_id custom fields for the accounting-desktop create
endpoints (Supplier, Purchase Invoice, Journal Entry, Warehouse) — Sales
Invoice, Payment Entry, Stock Entry, Customer, and Item already have this
field from earlier patches; these four did not.

Also invoked directly from zatgo_core.setup.ensure_custom_fields, which is
called from install.py's after_install/after_migrate — patches.txt alone
has been observed to not reliably materialize schema-critical custom
fields via `bench install-app`'s bundled patch execution, even though
Patch Log records them as successful. Don't remove this patch file (it's
still the standard/expected mechanism and keeps a normal `bench migrate`
working), but don't rely on it alone either.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    fields = {
        "Supplier": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "supplier_name",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
        "Purchase Invoice": [
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
        "Journal Entry": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "posting_date",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
        "Warehouse": [
            {
                "fieldname": "zatgo_client_id",
                "label": "ZatGo Client Id",
                "fieldtype": "Data",
                "insert_after": "warehouse_name",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "translatable": 0,
            }
        ],
    }
    filtered = {dt: defs for dt, defs in fields.items() if frappe.db.exists("DocType", dt)}
    if filtered:
        create_custom_fields(filtered, update=True)
        frappe.db.commit()
