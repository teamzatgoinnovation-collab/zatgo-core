"""Script Report: ZG Printer Usage."""

from __future__ import annotations

import frappe


def execute(filters=None):
    columns = [
        {"label": "Printer Role", "fieldname": "role", "fieldtype": "Data", "width": 160},
        {"label": "Device", "fieldname": "device", "fieldtype": "Data", "width": 220},
        {"label": "Configured", "fieldname": "configured", "fieldtype": "Check", "width": 100},
    ]
    if not frappe.db.exists("DocType", "ZG Printer Settings"):
        return columns, []
    doc = frappe.get_single("ZG Printer Settings")
    rows = [
        ("Receipt Printer", doc.receipt_printer),
        ("Kitchen Printer", doc.kitchen_printer),
        ("Barcode Printer", doc.barcode_printer),
        ("Label Printer", doc.label_printer),
        ("A4 Printer", doc.a4_printer),
    ]
    data = [
        {"role": role, "device": device or "", "configured": 1 if device else 0}
        for role, device in rows
    ]
    return columns, data

