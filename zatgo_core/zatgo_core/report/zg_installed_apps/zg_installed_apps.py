"""Script Report: ZG Installed Apps — site client applications."""

from __future__ import annotations

import frappe


def execute(filters=None):
    columns = [
        {"label": "App Key", "fieldname": "app_key", "fieldtype": "Data", "width": 160},
        {"label": "Title", "fieldname": "title", "fieldtype": "Data", "width": 180},
        {"label": "Platform", "fieldname": "platform", "fieldtype": "Data", "width": 100},
        {"label": "Enabled", "fieldname": "enabled", "fieldtype": "Check", "width": 80},
        {"label": "API Product", "fieldname": "api_product", "fieldtype": "Data", "width": 140},
        {
            "label": "Maintenance",
            "fieldname": "maintenance_mode",
            "fieldtype": "Check",
            "width": 110,
        },
        {
            "label": "Min Version",
            "fieldname": "minimum_version",
            "fieldtype": "Data",
            "width": 110,
        },
    ]
    if not frappe.db.exists("DocType", "ZG Application Settings"):
        return columns, []
    doc = frappe.get_single("ZG Application Settings")
    data = []
    for row in doc.get("client_apps") or []:
        data.append(
            {
                "app_key": row.app_key,
                "title": row.title,
                "platform": row.platform,
                "enabled": row.enabled,
                "api_product": row.api_product,
                "maintenance_mode": row.maintenance_mode,
                "minimum_version": row.minimum_version,
            }
        )
    return columns, data
