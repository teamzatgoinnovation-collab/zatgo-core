"""Script Report: ZG Feature Flags."""

from __future__ import annotations

import frappe


def execute(filters=None):
    columns = [
        {"label": "Flag Key", "fieldname": "flag_key", "fieldtype": "Data", "width": 180},
        {"label": "Title", "fieldname": "title", "fieldtype": "Data", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": "App", "fieldname": "app_name", "fieldtype": "Data", "width": 120},
        {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
        {"label": "Rollout %", "fieldname": "rollout_percent", "fieldtype": "Int", "width": 100},
    ]
    filters = filters or {}
    data = frappe.get_all(
        "ZG Feature Flag",
        filters=filters,
        fields=["flag_key", "title", "status", "app_name", "company", "rollout_percent"],
        order_by="flag_key asc",
        limit_page_length=1000,
    )
    return columns, data

