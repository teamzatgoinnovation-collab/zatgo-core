"""Script Report: ZG API Usage."""

from __future__ import annotations

import frappe


def execute(filters=None):
    """Summarize recent API-oriented audit / error activity."""
    columns = [
        {"label": "Metric", "fieldname": "metric", "fieldtype": "Data", "width": 220},
        {"label": "Value", "fieldname": "value", "fieldtype": "Int", "width": 120},
    ]
    audit_count = frappe.db.count("ZG Audit Log") if frappe.db.exists("DocType", "ZG Audit Log") else 0
    error_count = frappe.db.count("Error Log") if frappe.db.exists("DocType", "Error Log") else 0
    data = [
        {"metric": "ZG Audit Log rows", "value": audit_count},
        {"metric": "Error Log rows", "value": error_count},
        {"metric": "Installed apps", "value": len(frappe.get_installed_apps())},
    ]
    return columns, data

