"""Script Report: ZG Audit History."""

from __future__ import annotations

import frappe


def execute(filters=None):
    columns = [
        {"label": "Date", "fieldname": "change_date", "fieldtype": "Date", "width": 110},
        {"label": "Time", "fieldname": "change_time", "fieldtype": "Time", "width": 100},
        {"label": "DocType", "fieldname": "doctype_name", "fieldtype": "Data", "width": 160},
        {"label": "Document", "fieldname": "document_name", "fieldtype": "Data", "width": 160},
        {"label": "Field", "fieldname": "fieldname", "fieldtype": "Data", "width": 120},
        {"label": "Old Value", "fieldname": "old_value", "fieldtype": "Data", "width": 160},
        {"label": "New Value", "fieldname": "new_value", "fieldtype": "Data", "width": 160},
        {"label": "Changed By", "fieldname": "changed_by", "fieldtype": "Link", "options": "User", "width": 140},
        {"label": "IP", "fieldname": "ip_address", "fieldtype": "Data", "width": 120},
        {"label": "App", "fieldname": "app_name", "fieldtype": "Data", "width": 100},
    ]
    filters = filters or {}
    data = frappe.get_all(
        "ZG Audit Log",
        filters=filters,
        fields=[
            "change_date", "change_time", "doctype_name", "document_name", "fieldname",
            "old_value", "new_value", "changed_by", "ip_address", "app_name",
        ],
        order_by="creation desc",
        limit_page_length=1000,
    )
    return columns, data

