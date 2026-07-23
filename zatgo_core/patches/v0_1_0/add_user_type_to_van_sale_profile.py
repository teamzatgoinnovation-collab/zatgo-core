"""Ensure user_type field exists on ZG Van Sale Profile."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG Van Sale Profile"):
        return
    if not frappe.db.has_column("ZG Van Sale Profile", "user_type"):
        create_custom_fields(
            {
                "ZG Van Sale Profile": [
                    {
                        "fieldname": "user_type",
                        "fieldtype": "Select",
                        "label": "User Type",
                        "options": "Field User\nAdmin",
                        "default": "Field User",
                        "insert_after": "enabled",
                        "in_list_view": 1,
                        "in_standard_filter": 1,
                    }
                ]
            }
        )
