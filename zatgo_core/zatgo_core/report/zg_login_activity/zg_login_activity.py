"""Script Report: ZG Login Activity."""

from __future__ import annotations

import frappe


def execute(filters=None):
    columns = [
        {"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "IP Address", "fieldname": "ip_address", "fieldtype": "Data", "width": 140},
        {"label": "Operation", "fieldname": "operation", "fieldtype": "Data", "width": 120},
        {"label": "When", "fieldname": "creation", "fieldtype": "Datetime", "width": 160},
    ]
    if not frappe.db.exists("DocType", "Activity Log"):
        return columns, []
    data = frappe.get_all(
        "Activity Log",
        filters={"operation": ("in", ["Login", "Logout"])},
        fields=["user", "status", "ip_address", "operation", "creation"],
        order_by="creation desc",
        limit_page_length=500,
    )
    return columns, data

